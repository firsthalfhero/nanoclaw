# Start NanoClaw as a background process on Windows
# Usage: .\start.ps1

$root = $PSScriptRoot
$outLog = "$root\logs\nanoclaw-out.log"
$errLog = "$root\logs\nanoclaw-err.log"

# Ensure logs dir exists
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null

# Kill any existing NanoClaw process holding port 3001
$existing = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($existing) {
    Write-Host "Stopping existing process on port 3001 (PID $existing)..."
    Stop-Process -Id $existing -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Build first
Write-Host "Building..."
Push-Location $root
& npm run build 2>&1 | Out-Null
Pop-Location

# Start NanoClaw
$proc = Start-Process -FilePath "node" `
    -ArgumentList "dist/index.js" `
    -WorkingDirectory $root `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -NoNewWindow -PassThru

Write-Host "NanoClaw started (PID $($proc.Id))"
Write-Host "Logs: $outLog"
Write-Host ""
Write-Host "To stop:  Stop-Process -Id $($proc.Id) -Force"
Write-Host "To check: Get-Process -Id $($proc.Id) -ErrorAction SilentlyContinue"
Write-Host "To tail:  Get-Content $outLog -Wait"
