# Start NanoClaw with watchdog — restarts automatically if it crashes or is killed by sleep/lock.
# Usage: .\start.ps1 [-Debug]
param(
    [switch]$Debug
)

$root        = $PSScriptRoot
$outLog      = "$root\logs\nanoclaw-out.log"
$errLog      = "$root\logs\nanoclaw-err.log"
$watchdogLog = "$root\logs\nanoclaw-watchdog.log"

function Write-WatchdogLog($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -FilePath $watchdogLog -Append
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

# Use a lock file to prevent multiple watchdog instances.
$lockFile = "$root\logs\watchdog.lock"
if (Test-Path $lockFile) {
    $lockPid = Get-Content $lockFile -ErrorAction SilentlyContinue
    if ($lockPid -and (Get-Process -Id $lockPid -ErrorAction SilentlyContinue)) {
        Write-Host "Stopping existing NanoClaw watchdog (PID $lockPid)..." -ForegroundColor Yellow
        Stop-Process -Id $lockPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

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
    `$proc = Start-Process -FilePath "node" `
        -ArgumentList "dist/index.js" `
        -WorkingDirectory `$root `
        -RedirectStandardOutput `$outLog `
        -RedirectStandardError `$errLog `
        -NoNewWindow -PassThru

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
