#!/bin/bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="nanoclaw"

usage() {
  echo "Usage: $0 [start|stop|restart|status|logs]"
  echo "  start   — build then start via systemd"
  echo "  stop    — stop the systemd service"
  echo "  restart — build then restart via systemd (default)"
  echo "  status  — show service status"
  echo "  logs    — follow live logs"
  exit 1
}

CMD="${1:-restart}"

case "$CMD" in
  start|--start|-start)
    cd "$ROOT"
    echo "Building..."
    npm run build > /dev/null 2>&1 && echo "✓ Built" || { echo "❌ Build failed"; exit 1; }
    sudo systemctl start "$SERVICE"
    echo "✓ Started"
    ;;
  stop|--stop|-stop)
    sudo systemctl stop "$SERVICE"
    echo "✓ Stopped"
    ;;
  restart|--restart|-restart)
    cd "$ROOT"
    echo "Building..."
    npm run build > /dev/null 2>&1 && echo "✓ Built" || { echo "❌ Build failed"; exit 1; }
    sudo systemctl restart "$SERVICE"
    echo "✓ Restarted"
    echo ""
    echo "Logs: journalctl -u $SERVICE -f"
    ;;
  status|--status|-status)
    systemctl status "$SERVICE"
    ;;
  logs|--logs|-logs)
    journalctl -u "$SERVICE" -f
    ;;
  *)
    usage
    ;;
esac
