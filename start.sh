#!/bin/bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_LOG="$ROOT/logs/nanoclaw-out.log"
ERR_LOG="$ROOT/logs/nanoclaw-err.log"
WATCHDOG_LOG="$ROOT/logs/nanoclaw-watchdog.log"
LOCK_FILE="$ROOT/logs/watchdog.lock"

mkdir -p "$ROOT/logs"

write_watchdog_log() {
    local msg="$1"
    local ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$ts $msg" >> "$WATCHDOG_LOG"
}

# Nuclear option: kill EVERYTHING nanoclaw-related
cleanup_all() {
    echo "🔫 Killing all NanoClaw processes..."

    # Kill watchdog scripts
    pkill -9 -f "watchdog-script.sh" 2>/dev/null || true

    # Kill node processes
    pkill -9 -f "dist/index.js" 2>/dev/null || true
    pkill -9 node 2>/dev/null || true

    # Kill any bash running watchdog
    pkill -9 -f "watchdog" 2>/dev/null || true

    sleep 1

    # Force kill by port if still running
    while ss -tlnp 2>/dev/null | grep -q :3001; do
        echo "  Force killing process on :3001..."
        sudo fuser -k 3001/tcp 2>/dev/null || true
        sleep 1
    done

    echo "✓ All processes cleaned"
}

# Stop mode
if [ "$1" = "--stop" ] || [ "$1" = "-stop" ]; then
    cleanup_all
    rm -f "$LOCK_FILE"

    # Kill docker containers
    docker ps -q --filter name=nanoclaw- 2>/dev/null | xargs -r docker kill 2>/dev/null || true

    exit 0
fi

# Start mode
echo "================"
echo "NanoClaw Startup"
echo "================"

cleanup_all

# Verify port is free (with timeout)
WAIT=0
while [ $WAIT -lt 15 ]; do
    if ! ss -tlnp 2>/dev/null | grep -q :3001; then
        echo "✓ Port 3001 is free"
        break
    fi
    echo "⏳ Waiting for port 3001 to free... ($WAIT/15)"
    sleep 1
    WAIT=$((WAIT + 1))
done

if ss -tlnp 2>/dev/null | grep -q :3001; then
    echo "❌ ERROR: Port 3001 still in use after 15s"
    exit 1
fi

# Build
echo "Building..."
if ! npm run build > /dev/null 2>&1; then
    echo "❌ Build failed"
    exit 1
fi
echo "✓ Built"

# Start watchdog
echo "Starting watchdog..."
write_watchdog_log "=== Startup ==="

WATCHDOG_SCRIPT="$ROOT/logs/watchdog-script.sh"
cat > "$WATCHDOG_SCRIPT" << 'WATCHDOG'
#!/bin/bash
ROOT="$1"
OUT_LOG="$2"
ERR_LOG="$3"
WATCHDOG_LOG="$4"

write_watchdog_log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$WATCHDOG_LOG"
}

while true; do
    write_watchdog_log "Starting NanoClaw..."
    cd "$ROOT"

    node dist/index.js > "$OUT_LOG" 2> "$ERR_LOG" &
    PROC_PID=$!

    write_watchdog_log "Running (PID $PROC_PID)"
    wait $PROC_PID
    EXIT_CODE=$?

    write_watchdog_log "Exit code $EXIT_CODE - restarting in 5s..."
    sleep 5
done
WATCHDOG

chmod +x "$WATCHDOG_SCRIPT"

nohup bash "$WATCHDOG_SCRIPT" "$ROOT" "$OUT_LOG" "$ERR_LOG" "$WATCHDOG_LOG" > /dev/null 2>&1 &
WATCHDOG_PID=$!

echo "$WATCHDOG_PID" > "$LOCK_FILE"
echo "✓ Started (watchdog PID $WATCHDOG_PID)"
echo ""
echo "Logs:"
echo "  Live:    tail -f $WATCHDOG_LOG"
echo "  Output:  tail -f $OUT_LOG"
echo "  Errors:  tail -f $ERR_LOG"
