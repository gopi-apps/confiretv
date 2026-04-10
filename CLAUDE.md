# CLAUDE.md — ConFireTV Project Context

This file is read automatically by Claude Code at session start.
It captures the full context of this project so any new session can pick up where the last left off.

---

## What This Project Is

**ConFireTV** is a parental control and monitoring system for an Amazon Fire TV Stick.
It was built for a family in Bangalore, India — one child under 10 watches YouTube,
Disney+ Hotstar, Amazon Prime Video, and Sun NXT on a Panasonic 32" LED TV with a
Fire TV Stick on home WiFi.

**Problem Amazon's built-in Screen Time does NOT solve:**
- No per-app usage duration
- No usage history or analytics
- No remote kill from phone
- Very limited reporting in India

**Solution:** Python daemon that connects to Fire TV over ADB/WiFi, polls the
foreground app every 30 seconds, records sessions to SQLite, and serves a
mobile-friendly web dashboard on port 8000.

---

## Architecture

```
Fire TV Stick  --ADB/WiFi (port 5555)-->  Windows PC (always-on)
                                               |
                                         SQLite DB  (data/confiretvmonitor.db)
                                               |
                                         FastAPI   (port 8000)
                                               |
                              Browser on any phone/laptop on same WiFi
```

Three background processes run as Windows Services (via NSSM):
- **ConFireTV-Poller** — `python -m monitor.adb_poller` — polls Fire TV every 30s
- **ConFireTV-Web** — `uvicorn web.app:app --host 0.0.0.0 --port 8000` — dashboard
- **ConFireTV-Scheduler** — `python scheduler.py` — daily email report + bedtime enforcer

---

## Project Structure

```
ConFireTV/
├── monitor/
│   ├── adb_poller.py      # Core daemon: ADB polling, session tracking, auto-discovery
│   ├── db.py              # SQLite helpers: open/close sessions, daily totals, limits
│   └── notifier.py        # Gmail SMTP + ntfy.sh push notifications
├── web/
│   ├── app.py             # FastAPI: /api/status, /api/today, /api/kill-app, etc.
│   └── templates/
│       └── dashboard.html # Mobile-friendly dark UI with Chart.js
├── platform/
│   ├── windows/
│   │   ├── install_service.bat   # NSSM service installer (run as Administrator)
│   │   ├── manage.bat            # status/start/stop/logs
│   │   └── uninstall_service.bat
│   ├── macos/
│   │   ├── install_service.sh    # LaunchAgent installer
│   │   └── manage.sh
│   └── linux/
│       ├── install_service.sh    # systemd installer
│       ├── manage.sh
│       └── services/             # systemd .service templates
├── config.yaml            # GITIGNORED — real credentials live here
├── config.yaml.example    # Template committed to git
├── diagnose.py            # Step-by-step ADB troubleshooter
├── manage.py              # Cross-platform service manager (Python)
├── scheduler.py           # APScheduler: bedtime enforcer + daily email
├── requirements.txt       # fastapi, uvicorn, jinja2, pyyaml, apscheduler
└── CLAUDE.md              # This file
```

---

## config.yaml Key Values (User's Setup)

DO NOT commit real credentials. The actual `config.yaml` is gitignored.
This is the shape of the user's real config for reference:

```yaml
firetv:
  ip: "192.168.1.15"     # Fire TV Stick local IP
  port: 5555
  poll_interval: 30
  auto_discover: true    # scans /24 subnet after 3 failed connections

child:
  name: "Dhruv"
  daily_limit_minutes: 120

app_packages:
  youtube:
    package: "com.amazon.firetv.youtube"
  hotstar:
    package: "in.startv.hotstar"
  prime_video:
    package: "com.amazon.avod.thirdpartyclient"
  sun_next:
    package: "com.suntv.sunnxt"    # NOTE: verified on user's device
  firetv_home:
    package: "com.amazon.tv.launcher"

notifications:
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  # sender/recipient emails and app password are in gitignored config.yaml
  ntfy_topic: "confiretvmonitor-dhruv"
  daily_report_time: "21:00"
  alert_threshold_percent: 80

bedtime:
  enforce_time: "22:30"
  days: ["mon","tue","wed","thu","fri","sat","sun"]

database:
  path: "data/confiretvmonitor.db"
```

---

## Known Issues Fixed (do not reintroduce)

### 1. ADB connect bug
`connect()` must NOT use `-s IP:PORT` flag — the device isn't connected yet.
Separate function `_adb_connect_cmd()` runs `adb connect IP:PORT` without `-s`.
Using `adb(ip, port, "connect", ...)` adds `-s` which causes ADB to reject the command.

### 2. Wrong Sun NXT package name
The example had `com.sun.sunott` but the user's Fire TV has `com.suntv.sunnxt`.
Always use `python diagnose.py` to verify package names on the actual device.

### 3. Windows Service can't find adb.exe
Windows Services run as SYSTEM account with a minimal PATH.
Fix: NSSM `AppEnvironmentExtra` sets PATH to include the adb directory.
See `platform/windows/install_service.bat` — it auto-detects the adb path and injects it.

### 4. Windows Firewall blocking port 8000
Dashboard is not reachable from other devices on WiFi until firewall rule is added.
`install_service.bat` runs this automatically:
```batch
netsh advfirewall firewall add rule name="ConFireTV Dashboard" dir=in action=allow protocol=TCP localport=8000
```

### 5. install_service.bat encoding issues
The batch file MUST be:
- Pure ASCII (no Unicode, no em dashes, no box-drawing characters)
- CRLF line endings (not Unix LF)
- Windows null device `>nul` not Unix `>/dev/null`

The file in this repo is maintained with a Python script that writes it in binary
mode with explicit CRLF and ASCII-only content. Never edit it in a Mac text editor
and save — it will reintroduce LF endings or Unicode characters.

### 6. Fire TV IP changes after TV restart
Auto-discovery is enabled (`auto_discover: true`). After 3 failed connections,
`adb_poller.py` scans the entire /24 subnet in parallel (50 threads), verifies
each candidate is a Fire TV, and updates `config.yaml` automatically.
The user's ISP router does not support DHCP reservation.

### 7. Gmail App Password
User's Google account uses passkeys as primary sign-in, which hides the
App Passwords page. Direct URL: https://myaccount.google.com/apppasswords
Alternative: Brevo SMTP (see config.yaml.example Option B).

---

## How to Run on Windows (Setup Complete)

Prerequisites already met on the user's Windows PC:
- Python 3.9+ installed
- ADB (Android Platform Tools) installed at `C:\platform-tools\adb.exe`
- NSSM installed at `C:\Windows\System32\nssm.exe`
- venv exists at `<project>\venv\`
- `config.yaml` exists with real credentials

**Install/reinstall services:**
```batch
:: Run as Administrator
platform\windows\install_service.bat
```

**Daily management:**
```batch
platform\windows\manage.bat status
platform\windows\manage.bat logs
platform\windows\manage.bat stop
platform\windows\manage.bat start
```

Or cross-platform Python manager:
```batch
venv\Scripts\python manage.py status
venv\Scripts\python manage.py logs poller
```

**Diagnose ADB issues:**
```batch
venv\Scripts\python diagnose.py
```

**Dashboard URL (from any device on same WiFi):**
```
http://192.168.1.4:8000    (replace with the Windows PC's local IP)
```

---

## ADB Foreground Detection

`get_foreground_app()` in `monitor/adb_poller.py` tries 5 methods in order:
1. `dumpsys window` — primary (Fire OS 6/7/8)
2. `dumpsys window windows` — older Fire OS
3. `dumpsys activity activities` — activity manager
4. `dumpsys activity top` — top activity
5. `dumpsys SurfaceFlinger` — Amazon custom builds

If all fail, run `python diagnose.py` — it prints the raw ADB output so new
regex patterns can be added.

---

## Web API Routes

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/` | Dashboard HTML |
| GET | `/api/status` | Current app, session duration |
| GET | `/api/today` | Per-app totals + limits for today |
| GET | `/api/sessions` | Today's session timeline |
| GET | `/api/weekly` | Last 7 days per-app totals |
| POST | `/api/kill-app` | Force-stop current app on Fire TV |
| POST | `/api/set-limit` | Update per-app daily limit |
| POST | `/api/set-daily-limit` | Update total daily limit |
| GET | `/api/debug` | ADB diagnostics |
| GET | `/api/service-status` | Are the 3 services running? |

---

## Tech Stack

| Layer | Tech | Notes |
|-------|------|-------|
| ADB | subprocess + adb binary | `shutil.which()` finds adb cross-platform |
| DB | SQLite | `data/confiretvmonitor.db`, gitignored |
| Backend | FastAPI + Jinja2 | port 8000 |
| Frontend | HTML + Chart.js | dark mobile-friendly UI, no build step |
| Notifications | Gmail SMTP + ntfy.sh | ntfy topic: `confiretvmonitor-dhruv` |
| Scheduler | APScheduler | timezone: Asia/Kolkata |
| Services (Win) | NSSM | 3 services: Poller, Web, Scheduler |
| Services (Mac) | LaunchAgent | `platform/macos/` |
| Services (Linux) | systemd | `platform/linux/` |

---

## Development Notes

- The project is developed on macOS, deployed on Windows. When writing or editing
  `.bat` files, ALWAYS use the Python binary-write approach with CRLF endings.
  Never use a Mac text editor to save `.bat` files directly.
- `config.yaml` is gitignored. Real credentials are never committed.
- The `data/` directory (SQLite DB) and `logs/` directory are gitignored.
- `venv/` is gitignored.
- Timezone throughout: `Asia/Kolkata` (IST, UTC+5:30).
