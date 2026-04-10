# ConFireTV

**Parental control and monitoring system for Amazon Fire TV Stick.**  
Track screen time, per-app usage, and watching patterns — with a mobile-friendly web dashboard and instant push alerts.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

---

## Why ConFireTV?

Amazon's built-in Screen Time only lets you set a daily total limit — it gives no per-app usage data, no usage history, no remote kill, and has limited reporting in India. ConFireTV fills that gap using ADB over WiFi to monitor any app running on the Fire TV Stick, without installing anything on the TV itself.

---

## Features

- **Live status** — see which app is open right now and for how long
- **Per-app daily limits** — YouTube, Hotstar, Prime Video, Sun NXT (or any app)
- **Auto enforcement** — force-stops an app when its daily limit is reached
- **7-day usage chart** — stacked bar chart, per app
- **Session log** — full timeline of today's watching sessions
- **Remote kill** — "Stop TV Now" button from any phone/browser on your WiFi
- **Daily email report** — HTML summary sent every evening
- **Instant push alerts** — via ntfy.sh (free, no account, works on Android & iOS)
- **Bedtime enforcer** — kills all apps at a set time every night
- **Runs 24/7 as background services** — Windows (NSSM), macOS (LaunchAgent), Linux (systemd)
- **Cross-platform** — runs on Windows PC, Raspberry Pi, Mac, or any Linux machine

---

## How It Works

```
Amazon Fire TV Stick
       │
       │  ADB over WiFi (port 5555)
       │  polls every 30 seconds
       ▼
Home Server (Windows PC / Raspberry Pi / Mac)
  ├── monitor/adb_poller.py   → detects foreground app, records sessions to SQLite
  ├── scheduler.py            → sends daily report email at 9 PM, enforces bedtime
  └── web/app.py              → FastAPI dashboard on port 8000
       │
       │  HTTP (same WiFi)
       ▼
Any browser (phone, laptop, tablet)
  └── http://<server-ip>:8000
```

---

## Quick Start

### 1. Enable ADB on Fire TV (one-time, ~3 minutes)

1. Go to **Settings → My Fire TV → About**
2. Click the **Build** row **7 times** → "You are now a developer"
3. Go to **Settings → My Fire TV → Developer Options**
4. Turn **ADB Debugging → ON**
5. Note your Fire TV IP: **Settings → My Fire TV → About → Network**

### 2. Clone and configure

```bash
git clone https://github.com/your-username/ConFireTV.git
cd ConFireTV
cp config.yaml.example config.yaml
```

Edit `config.yaml`:
```yaml
firetv:
  ip: "192.168.1.105"   # ← your Fire TV IP

child:
  name: "Arjun"
  daily_limit_minutes: 120
```

### 3. Install Python dependencies

```bash
python -m venv venv

# Windows
venv\Scripts\pip install -r requirements.txt

# macOS / Linux
source venv/bin/activate && pip install -r requirements.txt
```

### 4. Test the connection

```bash
# Windows
venv\Scripts\python diagnose.py

# macOS / Linux
python diagnose.py
```

### 5. Install as background services

**Windows (recommended — runs even when you're not logged in):**
```
# Run as Administrator:
platform\windows\install_service.bat
```

**macOS:**
```bash
bash platform/macos/install_service.sh
```

**Linux / Raspberry Pi:**
```bash
sudo bash platform/linux/install_service.sh
```

### 6. Open the dashboard

From any device on the same WiFi:
```
http://<server-ip>:8000
```

---

## Dashboard

| Section | What it shows |
|---------|--------------|
| Live Status | Current app + elapsed time + Stop button |
| Today | Total watch time vs daily limit, per-app progress bars |
| 7 Days | Stacked bar chart of weekly usage per app |
| Sessions | Timeline of today's watching sessions |
| Settings | Edit per-app limits and daily total limit |

---

## Managing Services

```bash
# Cross-platform (Windows, macOS, Linux)
python manage.py status
python manage.py start
python manage.py stop
python manage.py restart
python manage.py logs             # tail all logs
python manage.py logs poller      # tail only the ADB poller log
```

**Windows only:**
```batch
platform\windows\manage.bat status
platform\windows\manage.bat logs
```

---

## Configuration Reference

See [`config.yaml.example`](config.yaml.example) for the full annotated template.

| Key | Description |
|-----|-------------|
| `firetv.ip` | Local IP address of your Fire TV Stick |
| `firetv.poll_interval` | Seconds between app checks (default: 30) |
| `child.daily_limit_minutes` | Total daily screen time limit |
| `app_limits.<app>` | Per-app daily limit in minutes (0 = no limit) |
| `app_packages.<app>.package` | Android package name — find with `adb shell pm list packages` |
| `notifications.ntfy_topic` | Your ntfy.sh topic for push notifications |
| `notifications.daily_report_time` | Time to send daily email (24h, local time) |
| `bedtime.enforce_time` | Time to force-stop all apps (24h, local time) |

---

## Finding App Package Names

If an app isn't being tracked, find its package name:

```bash
# Connect ADB first
adb connect <TV-IP>:5555

# Search by app name
adb -s <TV-IP>:5555 shell pm list packages | grep -i hotstar
adb -s <TV-IP>:5555 shell pm list packages | grep -i sun
adb -s <TV-IP>:5555 shell pm list packages | grep -i youtube
```

Add the result to `config.yaml` under `app_packages`.

---

## Push Notifications (ntfy.sh)

1. Install the **ntfy** app on your phone ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/app/ntfy/id1625396347))
2. Set a unique topic in `config.yaml` → `notifications.ntfy_topic`
3. In the ntfy app, subscribe to that topic
4. Done — you'll get instant push notifications when limits are hit

---

## Platform Requirements

| Component | Requirement |
|-----------|------------|
| Python | 3.9 or higher |
| ADB | Android Platform Tools ([download](https://developer.android.com/studio/releases/platform-tools)) |
| Fire TV | Any Fire TV Stick or Fire TV Cube with ADB Debugging enabled |
| Network | Server and Fire TV must be on the same WiFi/LAN |
| Windows service | [NSSM](https://nssm.cc/download) (for `install_service.bat`) |

---

## Project Structure

```
ConFireTV/
├── monitor/
│   ├── adb_poller.py      # ADB polling daemon — core of the system
│   ├── db.py              # SQLite session storage and queries
│   └── notifier.py        # Email + ntfy.sh notifications
├── web/
│   ├── app.py             # FastAPI web server + REST API
│   └── templates/
│       └── dashboard.html # Mobile-friendly dark UI
├── platform/
│   ├── windows/           # NSSM service installer + manage.bat
│   ├── macos/             # LaunchAgent installer + manage.sh
│   └── linux/             # systemd service files + install script
├── config.yaml.example    # Configuration template (copy to config.yaml)
├── diagnose.py            # ADB connection troubleshooter
├── manage.py              # Cross-platform service manager
├── scheduler.py           # Daily reports + bedtime enforcer
└── requirements.txt
```

---

## Troubleshooting

**"TV is idle" after 30 minutes:**
Run `python diagnose.py` — it will test every step and show the exact failure point.

**App not being tracked:**
Use `python diagnose.py` — it searches for the package name automatically and suggests the correct value for `config.yaml`.

**Dashboard not reachable from phone:**
Make sure your phone and the server are on the same WiFi. Use the server's local IP (e.g. `192.168.1.10:8000`), not `localhost`.

**Email not sending:**
Gmail requires an App Password, not your regular password. Generate one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). If that page is unavailable (passkey accounts), use [Brevo](https://www.brevo.com) SMTP — see `config.yaml.example`.

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first.

1. Fork the repo
2. Create a branch: `git checkout -b feature/your-feature`
3. Commit your changes
4. Push and open a Pull Request

---

## License

[MIT](LICENSE) — free to use, modify, and distribute.
