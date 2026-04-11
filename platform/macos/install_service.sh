#!/bin/bash
# ConFireTV — Install as macOS background services (LaunchAgents)
# Run once: bash install_service.sh
# After this, all 3 processes start at login and run silently in the background.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
VENV_UVICORN="$PROJECT_DIR/venv/bin/uvicorn"
LOGS_DIR="$PROJECT_DIR/logs"
LAUNCHD_DIR="$SCRIPT_DIR/launchd"
AGENTS_DIR="$HOME/Library/LaunchAgents"

BOLD="\033[1m"; GREEN="\033[92m"; RED="\033[91m"; YELLOW="\033[93m"; RESET="\033[0m"

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; exit 1; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $1"; }
head() { echo -e "\n${BOLD}$1${RESET}"; }

echo -e "\n${BOLD}ConFireTV — Service Installer${RESET}"
echo "================================================"

# ── Checks ──────────────────────────────────────────────────────────────────
head "1. Checking prerequisites"

[[ -f "$VENV_PYTHON" ]]   || fail "venv not found at $VENV_PYTHON. Run: python3 -m venv venv && pip install -r requirements.txt"
[[ -f "$VENV_UVICORN" ]]  || fail "uvicorn not found. Run: pip install -r requirements.txt"
[[ -f "$PROJECT_DIR/config.yaml" ]] || fail "config.yaml not found in $PROJECT_DIR"

ok "venv found: $VENV_PYTHON"
ok "Project: $PROJECT_DIR"
mkdir -p "$LOGS_DIR"
ok "Logs directory: $LOGS_DIR"

# ── Generate plist files ─────────────────────────────────────────────────────
head "2. Generating LaunchAgent plist files"

# Poller
cat > "$LAUNCHD_DIR/com.confiretvmonitor.poller.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.confiretvmonitor.poller</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>-m</string>
        <string>monitor.adb_poller</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>$LOGS_DIR/poller.log</string>
    <key>StandardErrorPath</key>
    <string>$LOGS_DIR/poller.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF
ok "poller.plist"

# Web server
cat > "$LAUNCHD_DIR/com.confiretvmonitor.web.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.confiretvmonitor.web</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_UVICORN</string>
        <string>web.app:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>StandardOutPath</key>
    <string>$LOGS_DIR/web.log</string>
    <key>StandardErrorPath</key>
    <string>$LOGS_DIR/web.log</string>
</dict>
</plist>
EOF
ok "web.plist"

# Scheduler
cat > "$LAUNCHD_DIR/com.confiretvmonitor.scheduler.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.confiretvmonitor.scheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>$PROJECT_DIR/scheduler.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>$LOGS_DIR/scheduler.log</string>
    <key>StandardErrorPath</key>
    <string>$LOGS_DIR/scheduler.log</string>
</dict>
</plist>
EOF
ok "scheduler.plist"

# ── Stop any manually running terminals ──────────────────────────────────────
head "3. Stopping any manually started processes"

pkill -f "monitor.adb_poller" 2>/dev/null && warn "Stopped running adb_poller" || true
pkill -f "uvicorn web.app"     2>/dev/null && warn "Stopped running web server"  || true
pkill -f "scheduler.py"        2>/dev/null && warn "Stopped running scheduler"   || true
sleep 1

# ── Install to LaunchAgents ──────────────────────────────────────────────────
head "4. Installing LaunchAgents"
mkdir -p "$AGENTS_DIR"

for svc in poller web scheduler; do
    PLIST_SRC="$LAUNCHD_DIR/com.confiretvmonitor.$svc.plist"
    PLIST_DST="$AGENTS_DIR/com.confiretvmonitor.$svc.plist"

    # Unload first if already loaded
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    cp "$PLIST_SRC" "$PLIST_DST"
    launchctl load -w "$PLIST_DST"
    ok "Loaded: com.confiretvmonitor.$svc"
done

# ── Verify ───────────────────────────────────────────────────────────────────
head "5. Verifying services started"
sleep 3

ALL_OK=true
for svc in poller web scheduler; do
    STATUS=$(launchctl list | grep "com.confiretvmonitor.$svc" | awk '{print $1}')
    if [[ "$STATUS" != "-" && -n "$STATUS" ]]; then
        ok "com.confiretvmonitor.$svc is running (PID: $STATUS)"
    else
        warn "com.confiretvmonitor.$svc — check logs: tail -f $LOGS_DIR/$svc.log"
        ALL_OK=false
    fi
done

echo ""
if $ALL_OK; then
    echo -e "${GREEN}${BOLD}All 3 services running in the background!${RESET}"
    echo ""
    echo "  Dashboard:  http://localhost:8000"
    echo "  Logs:       bash manage.sh logs"
    echo "  Status:     bash manage.sh status"
    echo "  Stop all:   bash manage.sh stop"
    echo ""
    echo "  Services auto-start at login and restart if they crash."
else
    echo -e "${YELLOW}Some services may not have started. Check logs:${RESET}"
    echo "  bash manage.sh logs"
fi
