# Start NanoClaw with watchdog — restarts automatically if it crashes or is killed by sleep/lock.
# Usage: .\start.ps1

$root = $PSScriptRoot
$outLog = "$root\logs\nanoclaw-out.log"
$errLog = "$root\logs\nanoclaw-err.log"
$watchdogLog = "$root\logs\nanoclaw-watchdog.log"

# Ensure logs dir exists
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null

# If NanoClaw is already running on port 3001, exit silently (handles session-unlock re-trigger)
$alreadyRunning = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue
if ($alreadyRunning) {
    exit 0
}

# Kill any existing NanoClaw process holding port 3001
$existing = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($existing) {
    Stop-Process -Id $existing -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Build first
Push-Location $root
& npm run build 2>&1 | Out-Null
Pop-Location

function Write-WatchdogLog($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Tee-Object -FilePath $watchdogLog -Append | Out-Null
}

Write-WatchdogLog "Watchdog started"

# Watchdog loop — restart NanoClaw whenever it exits
while ($true) {
    # Kill anything still on port 3001 before starting
    $existing = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
    if ($existing) {
        Stop-Process -Id $existing -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }

    Write-WatchdogLog "Starting NanoClaw..."
    $proc = Start-Process -FilePath "node" `
        -ArgumentList "dist/index.js" `
        -WorkingDirectory $root `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -NoNewWindow -PassThru

    Write-WatchdogLog "NanoClaw running (PID $($proc.Id))"
    $proc.WaitForExit()
    $code = $proc.ExitCode
    Write-WatchdogLog "NanoClaw exited (code $code) - restarting in 5s..."
    Start-Sleep -Seconds 5
}
