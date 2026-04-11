# ConFireTV — Setup Guide

End-to-end setup instructions for all supported platforms.

---

## Table of Contents

1. [Fire TV Stick — one-time setup](#1-fire-tv-stick--one-time-setup)
2. [Windows PC (recommended — always-on)](#2-windows-pc-recommended--always-on)
3. [macOS](#3-macos)
4. [Linux / Raspberry Pi](#4-linux--raspberry-pi)
5. [Accessing the dashboard remotely](#5-accessing-the-dashboard-remotely)
6. [Notifications setup](#6-notifications-setup)
7. [Finding correct app package names](#7-finding-correct-app-package-names)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Fire TV Stick — one-time setup

Do this once on the Fire TV. Takes about 3 minutes.

1. On the Fire TV remote, go to **Settings → My Fire TV → About**
2. Click the **"Build"** row **7 times quickly** → you'll see "You are now a developer"
3. Go back to **Settings → My Fire TV → Developer Options**
4. Set **ADB Debugging → ON**
5. Set **Apps from Unknown Sources → ON** (optional but useful)
6. Note your IP address:
   **Settings → My Fire TV → About → Network** → write down the IP (e.g. `192.168.1.15`)

> The first time ADB connects, the TV will show a popup asking  
> **"Allow ADB debugging from this computer?"**  
> Select **"Always allow from this computer"** and confirm.

---

## 2. Windows PC (recommended — always-on)

### Prerequisites

| Tool | Download | Notes |
|------|----------|-------|
| Python 3.9+ | [python.org](https://www.python.org/downloads/) | Check "Add to PATH" during install |
| Android Platform Tools | [developer.android.com](https://developer.android.com/studio/releases/platform-tools) | Extract to `C:\platform-tools`, add to PATH |
| NSSM | [nssm.cc/download](https://nssm.cc/download) | Extract `nssm.exe` to `C:\Windows\System32` |
| Git (optional) | [git-scm.com](https://git-scm.com/) | For cloning the repo |

**Add `C:\platform-tools` to Windows PATH:**  
Start → Search "Environment Variables" → System Properties → Environment Variables  
→ Under "System variables" → select `Path` → Edit → New → `C:\platform-tools` → OK

### Step-by-step

**1. Get the code**

```batch
git clone https://github.com/your-username/ConFireTV.git
cd ConFireTV
```

Or download and extract the ZIP from GitHub.

**2. Create the Python virtual environment**

```batch
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

**3. Configure**

```batch
copy config.yaml.example config.yaml
notepad config.yaml
```

Edit at minimum:
```yaml
firetv:
  ip: "192.168.1.100"   # ← your Fire TV IP

child:
  name: "Arjun"
  daily_limit_minutes: 120
```

**4. Test ADB connection**

Open a Command Prompt in the project folder:
```batch
adb connect 192.168.1.15:5555
adb -s 192.168.1.15:5555 shell echo ok
```

Both should succeed. If the second command shows a popup on the TV — accept it.

**5. Run the diagnostic**

```batch
venv\Scripts\python diagnose.py
```

This verifies the connection end-to-end and auto-detects correct package names.

**6. Install as Windows Services (run as Administrator)**

Right-click `platform\windows\install_service.bat` → **Run as administrator**

The batch file is a thin launcher — it calls `platform\windows\install.py`, which handles
the full installation in Python (avoiding cmd.exe batch parsing limitations).

It installs three Windows Services that start automatically at boot:
- `ConFireTV-Poller` — ADB monitoring daemon
- `ConFireTV-Web` — web dashboard on port 8000
- `ConFireTV-Scheduler` — daily report emails + bedtime

The installer also:
- Auto-detects `adb.exe` and injects its path into each service's environment
- Adds a Windows Firewall rule for port 8000
- Removes any pre-existing ConFireTV services before reinstalling

**7. Verify**

```batch
platform\windows\manage.bat status
```

You should see all three services as `[RUNNING]`.

**8. Open the dashboard**

From any device on the same WiFi:
```
http://<windows-pc-ip>:8000
```

Find your PC's IP: open Command Prompt → `ipconfig` → look for IPv4 Address under your WiFi adapter (e.g. `192.168.1.10`).

### Daily management (Windows)

```batch
platform\windows\manage.bat status     :: check if services are running
platform\windows\manage.bat stop       :: stop all services
platform\windows\manage.bat start      :: start all services
platform\windows\manage.bat logs       :: tail all logs live
platform\windows\manage.bat logs poller  :: tail only poller log
```

Or use the cross-platform manager:
```batch
venv\Scripts\python manage.py status
venv\Scripts\python manage.py logs
```

### Uninstalling (Windows)

```batch
platform\windows\uninstall_service.bat
```

---

## 3. macOS

### Prerequisites

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install ADB
brew install android-platform-tools

# Verify
adb version
```

### Step-by-step

```bash
git clone https://github.com/your-username/ConFireTV.git
cd ConFireTV

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp config.yaml.example config.yaml
nano config.yaml   # or open in any editor
```

Test connection:
```bash
adb connect 192.168.1.15:5555
python diagnose.py
```

Install as background services (auto-starts at login):
```bash
bash platform/macos/install_service.sh
```

Manage:
```bash
bash platform/macos/manage.sh status
bash platform/macos/manage.sh logs
python manage.py logs poller   # cross-platform alternative
```

---

## 4. Linux / Raspberry Pi

Recommended for an always-on, low-power server.

### Prerequisites

```bash
# Raspberry Pi OS / Ubuntu / Debian
sudo apt update
sudo apt install python3 python3-pip python3-venv adb -y
```

### Step-by-step

```bash
git clone https://github.com/your-username/ConFireTV.git
cd ConFireTV

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp config.yaml.example config.yaml
nano config.yaml
```

Test:
```bash
adb connect 192.168.1.15:5555
python diagnose.py
```

Install systemd services:
```bash
sudo bash platform/linux/install_service.sh
```

Manage:
```bash
bash platform/linux/manage.sh status
bash platform/linux/manage.sh logs
sudo systemctl status confiretvmonitor-poller
journalctl -u confiretvmonitor-poller -f    # live log via journald
```

---

## 5. Accessing the dashboard remotely

The web server binds to `0.0.0.0:8000` — accessible from any device on the same WiFi.

**Find your server's local IP:**

| Platform | Command |
|----------|---------|
| Windows | `ipconfig` → IPv4 Address |
| macOS | `ipconfig getifaddr en0` (WiFi) |
| Linux | `hostname -I` |

**Access the dashboard:**
```
http://192.168.1.10:8000       ← replace with your server's IP
```

Bookmark this URL on your phone. Works on any browser — Chrome, Safari, Firefox.

---

## 6. Notifications setup

### Push notifications (ntfy.sh — free, no account)

1. Install the **ntfy** app:
   - Android: [Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
   - iOS: [App Store](https://apps.apple.com/app/ntfy/id1625396347)
2. Choose a unique topic name (e.g. `confiretvmonitor-yourname-2024`)
3. Add to `config.yaml`:
   ```yaml
   notifications:
     ntfy_topic: "confiretvmonitor-yourname-2024"
   ```
4. In the ntfy app: tap **+** → enter the same topic name → Subscribe

You will now receive push notifications when:
- A daily limit is about to be hit (80% threshold)
- A limit is exceeded and the app is force-stopped
- The daily summary report is sent

### Email reports (Gmail)

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Name it "ConFireTV" → Create → copy the 16-character password
3. Add to `config.yaml`:
   ```yaml
   notifications:
     sender_email: "your@gmail.com"
     sender_app_password: "xxxx xxxx xxxx xxxx"
     recipient_email: "your@gmail.com"
   ```

> If the App Passwords page shows "page not found" (accounts using passkeys),
> use Brevo instead — see the commented Option B in `config.yaml.example`.

---

## 7. Finding correct app package names

Different Fire TV Stick models and regions use different package names. Always verify:

```bash
# Connect first
adb connect <TV-IP>:5555

# Search by keyword
adb -s <TV-IP>:5555 shell pm list packages | grep -i sun
adb -s <TV-IP>:5555 shell pm list packages | grep -i hotstar
adb -s <TV-IP>:5555 shell pm list packages | grep -i youtube
adb -s <TV-IP>:5555 shell pm list packages | grep -i amazon
```

Or run `python diagnose.py` — it does this automatically and suggests the correct `config.yaml` entries.

Update `config.yaml` with the correct package name:
```yaml
app_packages:
  sun_next:
    package: "com.sun.sunnxt"    # ← whatever adb returned
    display_name: "Sun NXT"
    color: "#FF6600"
```

---

## 8. Troubleshooting

### "TV is idle" — nothing is being tracked

1. Run `python diagnose.py` with an app open on the TV
2. Check the poller log: `python manage.py logs poller`
3. Most common causes:
   - ADB debugging was turned off on Fire TV (re-enable in Developer Options)
   - Fire TV IP changed (update `config.yaml` → `firetv.ip`)
   - "Allow ADB debugging?" popup on TV was not accepted

### "Connection refused" on `adb connect`

- ADB Debugging is OFF on the Fire TV → enable it in Developer Options
- Wrong IP in config.yaml

### App is running but not tracked

The package name in `config.yaml` doesn't match the actual installed package.  
Run `python diagnose.py` or: `adb -s <IP>:5555 shell pm list packages | grep -i <appname>`

### Services not starting on Windows

- Check the log: `platform\windows\manage.bat logs poller`
- Ensure `venv` is created and `pip install -r requirements.txt` completed
- Check `config.yaml` exists (not just `config.yaml.example`)
- Run `venv\Scripts\python diagnose.py` to verify ADB works
- If you moved `adb.exe` after installing, re-run `install_service.bat` as Administrator —
  it re-detects `adb.exe` and updates the service environment automatically

### Dashboard not reachable from phone

- Server and phone must be on the **same WiFi network**
- Use the server's LAN IP, not `localhost` (e.g. `http://192.168.1.10:8000`)
- Windows Firewall may be blocking port 8000 — allow it:
  `netsh advfirewall firewall add rule name="ConFireTV" dir=in action=allow protocol=TCP localport=8000`

### Email not sending

- Gmail: must use an App Password, not your login password
- Check for typos in `sender_app_password` — it should be exactly 16 characters with spaces
- Test manually: `python -c "from monitor.notifier import send_email; import yaml; cfg=yaml.safe_load(open('config.yaml')); send_email(cfg, 'Test', '<p>Test</p>')"`
