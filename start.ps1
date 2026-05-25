# Start or stop NanoClaw with watchdog — restarts automatically if it crashes or is killed by sleep/lock.
# Usage: .\start.ps1 [-Stop] [-Debug]
# Also supports --stop / --debug for convenience.
param(
    [switch]$Stop,
    [switch]$Debug
)

# Support --stop / --debug style arguments
if ($args -contains "--stop" -or $args -contains "-stop") {
    $Stop = $true
}
if ($args -contains "--debug" -or $args -contains "-debug") {
    $Debug = $true
}

$root        = $PSScriptRoot
$outLog      = "$root\logs\nanoclaw-out.log"
$errLog      = "$root\logs\nanoclaw-err.log"
$watchdogLog = "$root\logs\nanoclaw-watchdog.log"
$lockFile    = "$root\logs\watchdog.lock"

function Write-WatchdogLog($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -FilePath $watchdogLog -Append
}

# --- Stop mode ---
if ($Stop) {
    Write-Host "Stopping NanoClaw..." -ForegroundColor Yellow

    # Kill watchdog via lock file
    if (Test-Path $lockFile) {
        $lockPid = Get-Content $lockFile -ErrorAction SilentlyContinue
        if ($lockPid -and (Get-Process -Id $lockPid -ErrorAction SilentlyContinue)) {
            Write-Host "Stopping watchdog (PID $lockPid)..." -ForegroundColor Yellow
            Stop-Process -Id $lockPid -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    }

    # Kill any process holding port 3001
    $existing = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if ($existing) {
        foreach ($procId in $existing) {
            Write-Host "Stopping process on port 3001 (PID $procId)..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }

    # Kill agent containers
    $containers = & docker ps -q --filter name=nanoclaw- 2>$null
    if ($containers) {
        Write-Host "Killing agent containers..." -ForegroundColor Yellow
        $containers | ForEach-Object { & docker kill $_ 2>$null | Out-Null }
    }

    # Give processes a moment to exit
    Start-Sleep -Seconds 2

    # Verify nothing is left on port 3001
    $remaining = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue
    if (-not $remaining) {
        Write-Host "NanoClaw stopped successfully." -ForegroundColor Green
    } else {
        Write-Host "WARNING: Port 3001 may still be in use." -ForegroundColor Yellow
    }
    exit 0
}

# --- Start mode (original behavior) ---

# Check if Docker is running
try {
    $null = & docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker is not running"
    }
} catch {
    Write-Host "FATAL: Docker is not running. NanoClaw requires Docker to be running." -ForegroundColor Red
    Write-Host "Please start Docker Desktop or the Docker service and try again." -ForegroundColor Red
    exit 1
}

function Show-CompiledProxyCheck {
    $proxyJs = "$root\dist\credential-proxy.js"
    if (-not (Test-Path $proxyJs)) {
        Write-Host "  [WARN] dist/credential-proxy.js not found" -ForegroundColor Yellow
        return
    }
    $content = Get-Content $proxyJs -Raw
    $checks = @(
        @{ Label = "OpenRouter mode active log"; Pattern = "OpenRouter mode active" },
        @{ Label = "OPENROUTER_API_KEY read";    Pattern = "OPENROUTER_API_KEY" },
        @{ Label = "openrouter.ai upstream";     Pattern = "openrouter.ai" },
        @{ Label = "Bearer auth injection";      Pattern = "Bearer" },
        @{ Label = "pathPrefix logic";           Pattern = "pathPrefix" }
    )
    Write-Host "`n  dist/credential-proxy.js - OpenRouter support check:" -ForegroundColor Cyan
    foreach ($c in $checks) {
        if ($content -match $c.Pattern) {
            Write-Host ("  [OK]      " + $c.Label) -ForegroundColor Green
        } else {
            Write-Host ("  [MISSING] " + $c.Label) -ForegroundColor Red
        }
    }
    Write-Host ""
}

# Ensure logs dir exists
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null

# Kill any existing NanoClaw process holding port 3001
$existing = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($existing) {
    Write-Host "Stopping existing NanoClaw process (PID $existing)..." -ForegroundColor Yellow
    Stop-Process -Id $existing -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Force-kill any running agent containers before starting fresh
$containers = & docker ps -q --filter name=nanoclaw- 2>$null
if ($containers) {
    Write-Host "Killing running agent containers..." -ForegroundColor Yellow
    $containers | ForEach-Object { & docker kill $_ 2>$null | Out-Null }
}

# Build
Push-Location $root
Write-Host "Building NanoClaw..." -ForegroundColor Yellow
$buildResult = & npm.cmd run build 2>&1
$buildSuccess = $LASTEXITCODE -eq 0
Pop-Location

if (-not $buildSuccess) {
    Write-Host "Build failed:" -ForegroundColor Red
    $buildResult | Out-Host
    exit 1
}
Write-Host "Build succeeded." -ForegroundColor Green

# Verify build output exists
$agentEntry = "$root\dist\index.js"
if (-not (Test-Path $agentEntry)) {
    Write-Host "Build error: dist/index.js not found" -ForegroundColor Red
    exit 1
}

if ($Debug) { Show-CompiledProxyCheck }

Write-Host "Starting NanoClaw watchdog..." -ForegroundColor Cyan
Write-WatchdogLog "Watchdog started"

# Write watchdog script to a file — avoids -Command escaping/concatenation issues
$watchdogFile = "$root\logs\watchdog-script.ps1"
$watchdogContent = @"
`$root = "$root"
`$outLog = "$outLog"
`$errLog = "$errLog"
`$watchdogLog = "$watchdogLog"

function Write-WatchdogLog(`$msg) {
    `$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "`$ts `$msg" | Out-File -FilePath `$watchdogLog -Append
}

while (`$true) {
    `$existing = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
    if (`$existing) {
        Write-WatchdogLog "Killing process `$existing on port 3001..."
        Stop-Process -Id `$existing -Force -ErrorAction SilentlyContinue
    }

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
    `$proc = Start-Process -FilePath "node" -ArgumentList "dist/index.js" -WorkingDirectory `$root -RedirectStandardOutput `$outLog -RedirectStandardError `$errLog -NoNewWindow -PassThru

    if (-not `$proc) {
        Write-WatchdogLog "ERROR: Start-Process failed to create process"
        Start-Sleep -Seconds 5
        continue
    }

    Write-WatchdogLog "NanoClaw running (PID `$(`$proc.Id))"
    `$proc.WaitForExit()
    `$code = `$proc.ExitCode
    Write-WatchdogLog "NanoClaw exited (code `$code) - restarting in 5s..."
    Start-Sleep -Seconds 5
}
"@
$watchdogContent | Out-File -FilePath $watchdogFile -Encoding UTF8 -Force

$watchdogProc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $watchdogFile `
    -NoNewWindow -PassThru

# Write the child watchdog PID to the lock file so the next run can kill it cleanly.
$watchdogProc.Id | Out-File $lockFile -Force

Write-Host "NanoClaw watchdog started in background (PID $($watchdogProc.Id)). Check logs at $watchdogLog" -ForegroundColor Green
