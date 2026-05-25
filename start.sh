#!/bin/bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_LOG="$ROOT/logs/nanoclaw-out.log"
ERR_LOG="$ROOT/logs/nanoclaw-err.log"
WATCHDOG_LOG="$ROOT/logs/nanoclaw-watchdog.log"
LOCK_FILE="$ROOT/logs/watchdog.lock"

mkdir -p "$ROOT/logs"

# Kill EVERYTHING first - be super aggressive
echo "🔫 Nuclear cleanup..."

# Kill old watchdog PIDs if lock file exists
if [ -f "$LOCK_FILE" ]; then
    OLD_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ]; then
        kill -9 $OLD_PID 2>/dev/null || true
        echo "  Killed old watchdog $OLD_PID"
    fi
    rm -f "$LOCK_FILE"
fi

# Kill all watchdog scripts by looking in /proc
for pid in /proc/[0-9]*/; do
    if grep -q "watchdog-script.sh" "$pid/cmdline" 2>/dev/null; then
        PID=$(basename "$pid")
        kill -9 $PID 2>/dev/null || true
        echo "  Killed watchdog PID $PID"
    fi
done

# Kill all node processes in nanoclaw
for pid in /proc/[0-9]*/; do
    if grep -q "nanoclaw/dist/index.js" "$pid/cmdline" 2>/dev/null; then
        PID=$(basename "$pid")
        kill -9 $PID 2>/dev/null || true
        echo "  Killed node PID $PID"
    fi
done

sleep 2

# Verify everything is dead
if ps aux | grep -E "watchdog-script|nanoclaw/dist" | grep -v grep | grep -v "^$"; then
    echo "⚠️  WARNING: Some processes still alive, forcing..."
    ps aux | grep -E "watchdog-script|nanoclaw/dist" | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null || true
    sleep 2
fi

# Stop mode
if [ "$1" = "--stop" ] || [ "$1" = "-stop" ]; then
    echo "✓ Stopped"
    exit 0
fi

# Verify port is free
if ss -tlnp 2>/dev/null | grep -q :3001; then
    echo "❌ ERROR: Port 3001 still in use"
    ss -tlnp 2>/dev/null | grep 3001
    exit 1
fi
echo "✓ Port 3001 is free"

# Build
echo "Building..."
if ! npm run build > /dev/null 2>&1; then
    echo "❌ Build failed"
    exit 1
fi
echo "✓ Built"

# Start ONE watchdog only
echo "Starting watchdog..."

WATCHDOG_SCRIPT="$ROOT/logs/watchdog-script.sh"
cat > "$WATCHDOG_SCRIPT" << 'WATCHDOG'
#!/bin/bash
ROOT="$1"
OUT_LOG="$2"
ERR_LOG="$3"
WATCHDOG_LOG="$4"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Watchdog started" >> "$WATCHDOG_LOG"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting NanoClaw..." >> "$WATCHDOG_LOG"
    cd "$ROOT"

    node dist/index.js >> "$OUT_LOG" 2>> "$ERR_LOG" &
    PROC_PID=$!

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running (PID $PROC_PID)" >> "$WATCHDOG_LOG"
    wait $PROC_PID 2>/dev/null
    EXIT_CODE=$?

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Exit code $EXIT_CODE - restart in 5s..." >> "$WATCHDOG_LOG"
    sleep 5
done
WATCHDOG

chmod +x "$WATCHDOG_SCRIPT"

# Start watchdog
nohup bash "$WATCHDOG_SCRIPT" "$ROOT" "$OUT_LOG" "$ERR_LOG" "$WATCHDOG_LOG" > /dev/null 2>&1 &
WATCHDOG_PID=$!

echo "$WATCHDOG_PID" > "$LOCK_FILE"
echo "✓ Started (watchdog PID $WATCHDOG_PID)"
echo ""
echo "Logs: tail -f $WATCHDOG_LOG"
