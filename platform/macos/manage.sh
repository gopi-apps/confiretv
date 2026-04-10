#!/bin/bash
# ConFireTV — Service Manager
# Usage:
#   bash manage.sh status     — show if services are running
#   bash manage.sh start      — start all services
#   bash manage.sh stop       — stop all services
#   bash manage.sh restart    — restart all services
#   bash manage.sh logs       — tail live logs from all services
#   bash manage.sh logs poller|web|scheduler  — tail one service log

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="$PROJECT_DIR/logs"
AGENTS_DIR="$HOME/Library/LaunchAgents"
SERVICES=(poller web scheduler)

BOLD="\033[1m"; GREEN="\033[92m"; RED="\033[91m"; YELLOW="\033[93m"; CYAN="\033[96m"; RESET="\033[0m"

CMD="${1:-status}"

svc_label() { echo "com.confiretvmonitor.$1"; }
svc_plist() { echo "$AGENTS_DIR/com.confiretvmonitor.$1.plist"; }

# ── status ───────────────────────────────────────────────────────────────────
do_status() {
    echo -e "\n${BOLD}ConFireTV Service Status${RESET}"
    echo "─────────────────────────────────"
    for svc in "${SERVICES[@]}"; do
        LABEL=$(svc_label $svc)
        ROW=$(launchctl list | grep "$LABEL" 2>/dev/null)
        PID=$(echo "$ROW" | awk '{print $1}')
        EXIT=$(echo "$ROW" | awk '{print $2}')

        if [[ -n "$PID" && "$PID" != "-" ]]; then
            echo -e "  ${GREEN}● RUNNING${RESET}  $svc  (PID $PID)"
        elif [[ -n "$ROW" ]]; then
            echo -e "  ${RED}✗ STOPPED${RESET}  $svc  (last exit: $EXIT)"
        else
            echo -e "  ${YELLOW}○ NOT LOADED${RESET}  $svc"
        fi
    done
    echo ""
    echo -e "  Dashboard:  ${CYAN}http://localhost:8000${RESET}"
    echo -e "  Logs dir:   $LOGS_DIR"
    echo ""
}

# ── start ────────────────────────────────────────────────────────────────────
do_start() {
    echo -e "\n${BOLD}Starting ConFireTV services...${RESET}"
    for svc in "${SERVICES[@]}"; do
        PLIST=$(svc_plist $svc)
        if [[ ! -f "$PLIST" ]]; then
            echo -e "  ${RED}✗${RESET} $svc — not installed. Run: bash install_service.sh"
            continue
        fi
        launchctl load -w "$PLIST" 2>/dev/null || true
        sleep 1
        PID=$(launchctl list | grep "$(svc_label $svc)" | awk '{print $1}')
        if [[ -n "$PID" && "$PID" != "-" ]]; then
            echo -e "  ${GREEN}✓${RESET} $svc started (PID $PID)"
        else
            echo -e "  ${YELLOW}⚠${RESET} $svc may not have started — check: bash manage.sh logs $svc"
        fi
    done
}

# ── stop ─────────────────────────────────────────────────────────────────────
do_stop() {
    echo -e "\n${BOLD}Stopping ConFireTV services...${RESET}"
    for svc in "${SERVICES[@]}"; do
        PLIST=$(svc_plist $svc)
        launchctl unload "$PLIST" 2>/dev/null && \
            echo -e "  ${GREEN}✓${RESET} $svc stopped" || \
            echo -e "  ${YELLOW}○${RESET} $svc was not running"
    done
}

# ── restart ──────────────────────────────────────────────────────────────────
do_restart() {
    do_stop
    sleep 2
    do_start
}

# ── logs ─────────────────────────────────────────────────────────────────────
do_logs() {
    TARGET="${2:-}"
    if [[ -n "$TARGET" ]]; then
        LOG="$LOGS_DIR/$TARGET.log"
        [[ -f "$LOG" ]] || { echo "No log file at $LOG"; exit 1; }
        echo -e "${BOLD}Tailing $TARGET log (Ctrl+C to stop)${RESET}"
        tail -f "$LOG"
    else
        # Tail all 3 logs together using multitail or plain tail
        if command -v multitail &>/dev/null; then
            multitail -l "tail -f $LOGS_DIR/poller.log" \
                      -l "tail -f $LOGS_DIR/web.log" \
                      -l "tail -f $LOGS_DIR/scheduler.log"
        else
            echo -e "${BOLD}Tailing all logs (Ctrl+C to stop)${RESET}"
            echo -e "${CYAN}── poller ── web ── scheduler ──${RESET}\n"
            # Label each line with the source
            tail -f "$LOGS_DIR/poller.log"    2>/dev/null | sed 's/^/[poller]    /' &
            tail -f "$LOGS_DIR/web.log"       2>/dev/null | sed 's/^/[web]       /' &
            tail -f "$LOGS_DIR/scheduler.log" 2>/dev/null | sed 's/^/[scheduler] /' &
            wait
        fi
    fi
}

# ── dispatch ─────────────────────────────────────────────────────────────────
case "$CMD" in
    status)  do_status ;;
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_restart ;;
    logs)    do_logs "$@" ;;
    *)
        echo "Usage: bash manage.sh [status|start|stop|restart|logs [poller|web|scheduler]]"
        exit 1
        ;;
esac
