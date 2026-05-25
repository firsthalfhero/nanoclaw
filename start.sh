#!/bin/bash

# start.sh — Start NanoClaw on Linux
# Kills any existing instance, builds, and starts fresh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"

mkdir -p "$LOG_DIR"

echo "NanoClaw Startup"
echo "================"

# Kill existing process on port 3001
echo "Checking for existing process on port 3001..."
if lsof -i :3001 >/dev/null 2>&1; then
  PID=$(lsof -ti:3001)
  echo "Killing existing process (PID: $PID)..."
  kill -9 "$PID" || true
  sleep 1
fi

# Build
echo "Building project..."
cd "$PROJECT_ROOT"
npm run build

# Start
echo "Starting NanoClaw..."
npm start
