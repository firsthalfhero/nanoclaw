# Start NanoClaw with watchdog — restarts automatically if it crashes or is killed by sleep/lock.
# Usage: .\start.ps1

try {
$root = $PSScriptRoot
$outLog = "$root\logs\nanoclaw-out.log"
$errLog = "$root\logs\nanoclaw-err.log"
$watchdogLog = "$root\logs\nanoclaw-watchdog.log"

# Ensure logs dir exists
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null

# Use a lock file to prevent multiple watchdog instances.
# The lock file stores the PID of the child watchdog-script.ps1 process (not this script).
$lockFile = "$root\logs\watchdog.lock"
if (Test-Path $lockFile) {
    $lockPid = Get-Content $lockFile -ErrorAction SilentlyContinue
    if ($lockPid -and (Get-Process -Id $lockPid -ErrorAction SilentlyContinue)) {
        Write-Host "Stopping existing NanoClaw watchdog (PID $lockPid)..." -ForegroundColor Yellow
        Stop-Process -Id $lockPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}
# Lock file is written after the child watchdog process is started (below), so we have its PID.

# Kill any existing NanoClaw process holding port 3001
$existing = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($existing) {
    Write-Host "Stopping existing NanoClaw process (PID $existing)..." -ForegroundColor Yellow
    Stop-Process -Id $existing -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Force-kill any running agent containers before starting fresh
# (docker stop is graceful with 10s timeout; docker kill is instant)
$containers = & docker ps -q --filter name=nanoclaw- 2>$null
if ($containers) {
    Write-Host "Killing running agent containers..." -ForegroundColor Yellow
    $containers | ForEach-Object { & docker kill $_ 2>$null | Out-Null }
}

# Build first
Push-Location $root
Write-Host "Building NanoClaw..." -ForegroundColor Yellow
try {
    $buildResult = & npm.cmd run build 2>&1
    $buildSuccess = $LASTEXITCODE -eq 0
} catch {
    $buildSuccess = $false
    $buildResult = $_.Exception.Message
}
if (-not $buildSuccess) {
    Write-Host "Build failed:" -ForegroundColor Red
    $buildResult | Out-Host
    throw "Build failed"
} else {
    Write-Host "Build succeeded." -ForegroundColor Green
}
Pop-Location

function Write-WatchdogLog($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Tee-Object -FilePath $watchdogLog -Append | Out-Null
}

Write-Host "Starting NanoClaw watchdog..." -ForegroundColor Cyan
Write-WatchdogLog "Watchdog started"

# Write watchdog script to a file — avoids -Command escaping/concatenation issues
$watchdogFile = "$root\logs\watchdog-script.ps1"
@"
`$root = "$root"
`$outLog = "$outLog"
`$errLog = "$errLog"
`$watchdogLog = "$watchdogLog"

function Write-WatchdogLog(`$msg) {
    `$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "`$ts `$msg" | Out-File -FilePath `$watchdogLog -Append
}

# Watchdog loop - restart NanoClaw whenever it exits
while (`$true) {
    # Kill anything still on port 3001 before starting
    `$existing = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
    if (`$existing) {
        Write-WatchdogLog "Killing process `$existing on port 3001..."
        Stop-Process -Id `$existing -Force -ErrorAction SilentlyContinue
    }

    # Wait for port 3001 to be free - Windows TCP sockets stay in TIME_WAIT for
    # up to 120s after a kill. Without this, the new instance hits EADDRINUSE on
    # startup and exits immediately, causing a rapid crash-restart loop.
    `$maxWait = 15
    `$waited = 0
    while ((Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue) -and (`$waited -lt `$maxWait)) {
        `$waited++
        Write-WatchdogLog "Port 3001 still in use, waiting... (`$waited/`$maxWait)"
        Start-Sleep -Seconds 1
    }
    if (Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue) {
        Write-WatchdogLog "WARNING: port 3001 still occupied after `$maxWait s - proceeding anyway"
    }

    Write-WatchdogLog "Starting NanoClaw..."
    `$proc = Start-Process -FilePath "node" ``
        -ArgumentList "dist/index.js" ``
        -WorkingDirectory `$root ``
        -RedirectStandardOutput `$outLog ``
        -RedirectStandardError `$errLog ``
        -NoNewWindow -PassThru

    Write-WatchdogLog "NanoClaw running (PID `$(`$proc.Id))"
    `$proc.WaitForExit()
    `$code = `$proc.ExitCode
    Write-WatchdogLog "NanoClaw exited (code `$code) - restarting in 5s..."
    Start-Sleep -Seconds 5
}
"@ | Out-File -FilePath $watchdogFile -Encoding UTF8 -Force

$watchdogProc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-ExecutionPolicy", "Bypass", "-File", $watchdogFile `
    -NoNewWindow -PassThru

# Write the child watchdog PID to the lock file so the next run can kill it cleanly.
$watchdogProc.Id | Out-File $lockFile -Force

Write-Host "NanoClaw watchdog started in background (PID $($watchdogProc.Id)). Check logs at $watchdogLog" -ForegroundColor Green
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
