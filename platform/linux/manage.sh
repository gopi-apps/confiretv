#!/bin/bash
# ConFireTV Linux service manager
# Usage: bash manage.sh [status|start|stop|restart|logs [poller|web|scheduler]]
CMD="${1:-status}"
SVCS=(poller web scheduler)
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

GREEN="\033[92m"; RED="\033[91m"; YELLOW="\033[93m"; RESET="\033[0m"

case "$CMD" in
  status)
    echo -e "\nConFireTV Service Status"
    echo "────────────────────────"
    for s in "${SVCS[@]}"; do
      STATUS=$(systemctl is-active "confiretvmonitor-$s" 2>/dev/null)
      [[ "$STATUS" == "active" ]] && echo -e "  ${GREEN}● RUNNING${RESET}  confiretvmonitor-$s" \
                                  || echo -e "  ${RED}✗ $STATUS${RESET}   confiretvmonitor-$s"
    done
    echo -e "\n  Dashboard: http://localhost:8000\n"
    ;;
  start)
    for s in "${SVCS[@]}"; do sudo systemctl start "confiretvmonitor-$s" && echo "Started $s"; done ;;
  stop)
    for s in "${SVCS[@]}"; do sudo systemctl stop "confiretvmonitor-$s" && echo "Stopped $s"; done ;;
  restart)
    for s in "${SVCS[@]}"; do sudo systemctl restart "confiretvmonitor-$s" && echo "Restarted $s"; done ;;
  logs)
    TARGET="${2:-}"
    if [[ -n "$TARGET" ]]; then
      journalctl -u "confiretvmonitor-$TARGET" -f -n 50
    else
      # Tail all log files
      tail -f "$PROJECT_DIR/logs/poller.log"    2>/dev/null | sed 's/^/[poller]    /' &
      tail -f "$PROJECT_DIR/logs/web.log"       2>/dev/null | sed 's/^/[web]       /' &
      tail -f "$PROJECT_DIR/logs/scheduler.log" 2>/dev/null | sed 's/^/[scheduler] /' &
      wait
    fi
    ;;
  *)
    echo "Usage: bash manage.sh [status|start|stop|restart|logs [poller|web|scheduler]]"
    ;;
esac
