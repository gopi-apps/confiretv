# CLAUDE.md — ConFireTV Developer Context

This file is read automatically by Claude Code at session start.
It provides architectural context, known gotchas, and quick-start commands for contributors.

---

## What This Project Is

**ConFireTV** is an open-source parental control and monitoring system for Amazon Fire TV Stick.
It solves the gap in Amazon's built-in Screen Time: no per-app usage duration, no history,
no remote kill, and no useful reporting.

**Solution:** Python daemon that connects to Fire TV over ADB/WiFi, polls the foreground app
every 30 seconds, records sessions to SQLite, and serves a mobile-friendly web dashboard
on port 8000. Works on any home WiFi network without installing anything on the TV.

---

## Architecture

```
Fire TV Stick  --ADB/WiFi (port 5555)-->  Home server (Windows / macOS / Linux)
                                               |
                                         SQLite DB  (data/confiretvmonitor.db)
                                               |
                                         FastAPI   (port 8000)
                                               |
                              Browser on any phone/laptop on same WiFi
```

Three background processes:
- **ConFireTV-Poller** — `python -m monitor.adb_poller` — polls Fire TV every 30s
- **ConFireTV-Web** — `uvicorn web.app:app --host 0.0.0.0 --port 8000` — dashboard
- **ConFireTV-Scheduler** — `python scheduler.py` — daily email report + bedtime enforcer

Service management: **NSSM** (Windows), **LaunchAgent** (macOS), **systemd** (Linux).

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
│   │   ├── install_service.bat   # Thin launcher → calls install.py as Administrator
│   │   ├── install.py            # Python installer: NSSM service setup + firewall
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

## config.yaml Shape

`config.yaml` is gitignored. See `config.yaml.example` for the full annotated template.
Key fields:

```yaml
firetv:
  ip: "192.168.1.100"     # Fire TV Stick local IP
  port: 5555
  poll_interval: 30
  auto_discover: true     # scans /24 subnet after 3 failed connections

child:
  name: "Arjun"
  daily_limit_minutes: 120

app_packages:
  youtube:
    package: "com.amazon.firetv.youtube"
  hotstar:
    package: "in.startv.hotstar"
  prime_video:
    package: "com.amazon.avod.thirdpartyclient"
  sun_next:
    package: "com.sun.sunnxt"    # verify with: python diagnose.py
  firetv_home:
    package: "com.amazon.tv.launcher"

notifications:
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  ntfy_topic: "confiretvmonitor-yourname"
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

### 2. Sun NXT package name varies by device/region
Common variants: `com.sun.sunnxt`, `com.suntv.sunnxt`, `com.sun.sunott`.
Always use `python diagnose.py` to verify the correct package name on the target device.

### 3. Windows Service can't find adb.exe
Windows Services run as the SYSTEM account with a minimal PATH.
Fix: `install.py` auto-detects `adb.exe` via `shutil.which()` + known candidate paths,
then sets NSSM `AppEnvironmentExtra` to inject the adb directory into each service's PATH.

### 4. Windows Firewall blocking port 8000
Dashboard is not reachable from other devices on WiFi until a firewall inbound rule is added.
`install.py` runs this automatically:
```batch
netsh advfirewall firewall add rule name="ConFireTV Dashboard" dir=in action=allow protocol=TCP localport=8000
```

### 5. install_service.bat replaced with Python installer
The original batch file failed with `. was unexpected at this time.` when run as Administrator
on Windows 11 (admin-context cmd.exe parsing quirk). The file is now a 3-line Python launcher:
```batch
@echo off
python "%~dp0..\..\venv\Scripts\python.exe" "%~dp0install.py" %*
pause
```
All installation logic lives in `platform/windows/install.py`.
If editing the `.bat` file, write it in binary mode with explicit CRLF to avoid encoding issues.

### 6. Fire TV IP changes after restart
Auto-discovery is enabled by default (`auto_discover: true`). After 3 failed connections,
`adb_poller.py` scans the entire /24 subnet in parallel (50 threads), verifies each
candidate is a Fire TV (checks for the launcher package), and updates `config.yaml` automatically.
Disable with `auto_discover: false` if using DHCP reservation on your router.

### 7. Gmail App Password
Gmail requires an App Password (not your login password).
Generate one at: https://myaccount.google.com/apppasswords
If that page is unavailable, use Brevo SMTP instead — see `config.yaml.example` Option B.

### 8. macOS installer PROJECT_DIR bug (fixed)
`platform/macos/install_service.sh` previously resolved `PROJECT_DIR` to `platform/macos/`
instead of the project root. Fixed by splitting into `SCRIPT_DIR` + `/../..`:
```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LAUNCHD_DIR="$SCRIPT_DIR/launchd"
```

---

## Quick Start (any platform)

```bash
# 1. Clone and configure
git clone <repo-url>
cd ConFireTV
cp config.yaml.example config.yaml
# Edit config.yaml: set firetv.ip, child.name, notification credentials

# 2. Python environment
python -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate           # Windows

pip install -r requirements.txt

# 3. Verify ADB connection (TV must be on with ADB Debugging enabled)
python diagnose.py

# 4. Install background services
bash platform/macos/install_service.sh       # macOS
sudo bash platform/linux/install_service.sh  # Linux
# Windows: right-click platform\windows\install_service.bat → Run as administrator
```

---

## ADB Foreground Detection

`get_foreground_app()` in `monitor/adb_poller.py` tries 5 methods in order:
1. `dumpsys window` — primary (Fire OS 6/7/8)
2. `dumpsys window windows` — older Fire OS
3. `dumpsys activity activities` — activity manager
4. `dumpsys activity top` — top activity
5. `dumpsys SurfaceFlinger` — Amazon custom builds

If all fail, run `python diagnose.py` — it prints raw ADB output so new regex patterns
can be added to `get_foreground_app()`.

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
| Notifications | Gmail SMTP + ntfy.sh | configure topic in `config.yaml` |
| Scheduler | APScheduler | timezone: configurable (default Asia/Kolkata) |
| Services (Win) | NSSM | 3 services: Poller, Web, Scheduler |
| Services (Mac) | LaunchAgent | `platform/macos/` |
| Services (Linux) | systemd | `platform/linux/` |
