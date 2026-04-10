#!/bin/bash
# ConFireTV — Linux/Raspberry Pi Service Installer (systemd)
# Run once:  sudo bash install_service.sh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
VENV_UVICORN="$PROJECT_DIR/venv/bin/uvicorn"
SERVICE_SRC="$(dirname "$0")/services"
SYSTEMD_DIR="/etc/systemd/system"
CURRENT_USER="${SUDO_USER:-$USER}"

GREEN="\033[92m"; RED="\033[91m"; YELLOW="\033[93m"; BOLD="\033[1m"; RESET="\033[0m"
ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; exit 1; }
head() { echo -e "\n${BOLD}$1${RESET}"; }

echo -e "\n${BOLD}ConFireTV — Linux Service Installer${RESET}"
echo "============================================"

[[ $EUID -eq 0 ]] || fail "Run as root: sudo bash install_service.sh"
[[ -f "$VENV_PYTHON" ]]   || fail "venv not found. Run: python3 -m venv venv && pip install -r requirements.txt"
[[ -f "$PROJECT_DIR/config.yaml" ]] || fail "config.yaml not found. Copy config.yaml.example and fill in your settings."

ok "Project: $PROJECT_DIR"
ok "User: $CURRENT_USER"
mkdir -p "$PROJECT_DIR/logs"
ok "Logs: $PROJECT_DIR/logs"

head "Installing systemd services"

for SVC in poller web scheduler; do
    TEMPLATE="$SERVICE_SRC/confiretvmonitor-$SVC.service"
    TARGET="$SYSTEMD_DIR/confiretvmonitor-$SVC.service"

    # Substitute placeholders with real paths
    sed \
        -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
        -e "s|__VENV_PYTHON__|$VENV_PYTHON|g" \
        -e "s|__VENV_UVICORN__|$VENV_UVICORN|g" \
        -e "s|__USER__|$CURRENT_USER|g" \
        "$TEMPLATE" > "$TARGET"

    systemctl daemon-reload
    systemctl enable "confiretvmonitor-$SVC"
    systemctl restart "confiretvmonitor-$SVC"
    ok "confiretvmonitor-$SVC enabled and started"
done

head "Status"
for SVC in poller web scheduler; do
    STATUS=$(systemctl is-active "confiretvmonitor-$SVC")
    if [[ "$STATUS" == "active" ]]; then
        ok "confiretvmonitor-$SVC is running"
    else
        echo -e "  ${YELLOW}⚠${RESET} confiretvmonitor-$SVC status: $STATUS — check: journalctl -u confiretvmonitor-$SVC -n 30"
    fi
done

echo -e "\n${GREEN}${BOLD}Done!${RESET}"
echo "  Dashboard: http://localhost:8000"
echo "  Manage:    bash platform/linux/manage.sh status|start|stop|logs"
