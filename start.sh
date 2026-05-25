#!/bin/bash
# Start or stop NanoClaw with watchdog — restarts automatically if it crashes or is killed by sleep/lock.
# Usage: ./start.sh [--stop] [--debug]

set -e

# Parse arguments
STOP=false
DEBUG=false

for arg in "$@"; do
    case "$arg" in
        --stop|-stop)
            STOP=true
            ;;
        --debug|-debug)
            DEBUG=true
            ;;
    esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_LOG="$ROOT/logs/nanoclaw-out.log"
ERR_LOG="$ROOT/logs/nanoclaw-err.log"
WATCHDOG_LOG="$ROOT/logs/nanoclaw-watchdog.log"
LOCK_FILE="$ROOT/logs/watchdog.lock"

write_watchdog_log() {
    local msg="$1"
    local ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$ts $msg" >> "$WATCHDOG_LOG"
}

# Function to get PID of process using port 3001
get_port_pid() {
    lsof -i :3001 -t 2>/dev/null | head -n1
}

# --- Stop mode ---
if [ "$STOP" = true ]; then
    echo "Stopping NanoClaw..."

    # Kill watchdog via lock file
    if [ -f "$LOCK_FILE" ]; then
        LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null)
        if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
            echo "Stopping watchdog (PID $LOCK_PID)..."
            kill -9 "$LOCK_PID" 2>/dev/null || true
        fi
        rm -f "$LOCK_FILE"
    fi

    # Kill any process holding port 3001
    PORT_PID=$(get_port_pid)
    if [ -n "$PORT_PID" ]; then
        echo "Stopping process on port 3001 (PID $PORT_PID)..."
        kill -9 "$PORT_PID" 2>/dev/null || true
    fi

    # Kill agent containers
    CONTAINERS=$(docker ps -q --filter name=nanoclaw- 2>/dev/null || true)
    if [ -n "$CONTAINERS" ]; then
        echo "Killing agent containers..."
        echo "$CONTAINERS" | xargs -r docker kill 2>/dev/null || true
    fi

    # Give processes a moment to exit
    sleep 2

    # Verify nothing is left on port 3001
    if ! get_port_pid > /dev/null 2>&1; then
        echo "✓ NanoClaw stopped successfully."
    else
        echo "⚠ WARNING: Port 3001 may still be in use."
    fi
    exit 0
fi

# --- Start mode (original behavior) ---

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "✗ FATAL: Docker is not running. NanoClaw requires Docker to be running."
    echo "Please start Docker and try again."
    exit 1
fi

show_compiled_proxy_check() {
    local proxy_js="$ROOT/dist/credential-proxy.js"
    if [ ! -f "$proxy_js" ]; then
        echo "  [WARN] dist/credential-proxy.js not found"
        return
    fi

    echo ""
    echo "  dist/credential-proxy.js - OpenRouter support check:"

    local checks=(
        "OpenRouter mode active:OpenRouter mode active"
        "OPENROUTER_API_KEY read:OPENROUTER_API_KEY"
        "openrouter.ai upstream:openrouter.ai"
        "Bearer auth injection:Bearer"
        "pathPrefix logic:pathPrefix"
    )

    for check in "${checks[@]}"; do
        local label="${check%%:*}"
        local pattern="${check##*:}"

        if grep -q "$pattern" "$proxy_js"; then
            echo "  [OK]      $label"
        else
            echo "  [MISSING] $label"
        fi
    done
    echo ""
}

# Ensure logs dir exists
mkdir -p "$ROOT/logs"

# Kill any existing NanoClaw process holding port 3001
PORT_PID=$(get_port_pid)
if [ -n "$PORT_PID" ]; then
    echo "Stopping existing NanoClaw process (PID $PORT_PID)..."
    kill -9 "$PORT_PID" 2>/dev/null || true
    sleep 2
fi

# Force-kill any running agent containers before starting fresh
CONTAINERS=$(docker ps -q --filter name=nanoclaw- 2>/dev/null || true)
if [ -n "$CONTAINERS" ]; then
    echo "Killing running agent containers..."
    echo "$CONTAINERS" | xargs -r docker kill 2>/dev/null || true
fi

# Build
cd "$ROOT"
echo "Building NanoClaw..."
if ! npm run build > /dev/null 2>&1; then
    echo "✗ Build failed. Run 'npm run build' for details."
    exit 1
fi
echo "✓ Build succeeded."

# Verify build output exists
if [ ! -f "$ROOT/dist/index.js" ]; then
    echo "✗ Build error: dist/index.js not found"
    exit 1
fi

if [ "$DEBUG" = true ]; then
    show_compiled_proxy_check
fi

echo "Starting NanoClaw watchdog..."
write_watchdog_log "Watchdog started"

# Write watchdog script to a file
WATCHDOG_FILE="$ROOT/logs/watchdog-script.sh"
cat > "$WATCHDOG_FILE" << 'WATCHDOG_SCRIPT'
#!/bin/bash

ROOT="$1"
OUT_LOG="$2"
ERR_LOG="$3"
WATCHDOG_LOG="$4"

write_watchdog_log() {
    local msg="$1"
    local ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$ts $msg" >> "$WATCHDOG_LOG"
}

get_port_pid() {
    lsof -i :3001 -t 2>/dev/null | head -n1
}

while true; do
    PORT_PID=$(get_port_pid)
    if [ -n "$PORT_PID" ]; then
        write_watchdog_log "Killing process $PORT_PID on port 3001..."
        kill -9 "$PORT_PID" 2>/dev/null || true
    fi

    MAX_WAIT=15
    WAITED=0
    while [ -n "$(get_port_pid)" ] && [ $WAITED -lt $MAX_WAIT ]; do
        WAITED=$((WAITED + 1))
        write_watchdog_log "Port 3001 still in use, waiting... ($WAITED/$MAX_WAIT)"
        sleep 1
    done

    if [ -n "$(get_port_pid)" ]; then
        write_watchdog_log "WARNING: port 3001 still occupied after $MAX_WAIT s - proceeding anyway"
    fi

    write_watchdog_log "Starting NanoClaw..."
    cd "$ROOT"
    node dist/index.js > "$OUT_LOG" 2> "$ERR_LOG" &
    PROC_PID=$!

    if [ -z "$PROC_PID" ]; then
        write_watchdog_log "ERROR: Failed to start process"
        sleep 5
        continue
    fi

    write_watchdog_log "NanoClaw running (PID $PROC_PID)"
    wait $PROC_PID
    EXIT_CODE=$?
    write_watchdog_log "NanoClaw exited (code $EXIT_CODE) - restarting in 5s..."
    sleep 5
done
WATCHDOG_SCRIPT

chmod +x "$WATCHDOG_FILE"

# Start the watchdog script in the background
nohup bash "$WATCHDOG_FILE" "$ROOT" "$OUT_LOG" "$ERR_LOG" "$WATCHDOG_LOG" > /dev/null 2>&1 &
WATCHDOG_PID=$!

# Write the watchdog PID to the lock file so the next run can kill it cleanly
echo "$WATCHDOG_PID" > "$LOCK_FILE"

echo "✓ NanoClaw watchdog started in background (PID $WATCHDOG_PID)"
echo "  Logs: $WATCHDOG_LOG"
