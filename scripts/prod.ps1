<#
.SYNOPSIS
    Run LifeOS for everyday use on this computer.

    One hidden API process serves both the API and the built web client on
    http://127.0.0.1:8080 (only this computer can reach it). Tailscale publishes it to
    your devices with HTTPS:  tailscale serve --bg 8080

        powershell -ExecutionPolicy Bypass -File .\scripts\prod.ps1          # start
        powershell -ExecutionPolicy Bypass -File .\scripts\prod.ps1 -Status
        powershell -ExecutionPolicy Bypass -File .\scripts\prod.ps1 -Stop
        powershell -ExecutionPolicy Bypass -File .\scripts\prod.ps1 -Build   # force a client rebuild

    On start the script also starts PostgreSQL, makes the daily backup, applies
    migrations and rebuilds the web client when its sources changed. It can run next to
    the development servers (ports 8000 and 5173). Logs: %LOCALAPPDATA%\LifeOS\api.log
#>
param([switch]$Build, [switch]$Stop, [switch]$Status)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Port = 8080
$StateDir = Join-Path $env:LOCALAPPDATA 'LifeOS'
$LogFile = Join-Path $StateDir 'api.log'

# A terminal opened before Node.js or Python were installed still has the old PATH.
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')

$python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
$webDir = Join-Path $Root 'web'
$dist = Join-Path $webDir 'dist\index.html'

function Test-Health {
    try { return ((Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3).status -eq 'ok') }
    catch { return $false }
}

function Get-TailscaleUrl {
    $tailscale = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
    if (-not (Test-Path -LiteralPath $tailscale)) { return $null }
    try {
        $state = & $tailscale status --json | ConvertFrom-Json
        $name = "$($state.Self.DNSName)".TrimEnd('.')
        if ($name) { return "https://$name" }
    }
    catch { }
    return $null
}

function Stop-Api {
    # Stopping the process that listens on the port is enough: the virtualenv launcher
    # and the hidden PowerShell that started it exit right after it.
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($processId in ($listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
        & taskkill.exe /F /T /PID $processId | Out-Null
    }
}

function Test-ClientOutdated {
    if ($Build -or -not (Test-Path -LiteralPath $dist)) { return $true }
    $built = (Get-Item -LiteralPath $dist).LastWriteTimeUtc
    $sources = @(
        (Join-Path $webDir 'src'),
        (Join-Path $webDir 'public'),
        (Join-Path $webDir 'index.html'),
        (Join-Path $webDir 'vite.config.ts')
    )
    $newest = Get-ChildItem -LiteralPath $sources -Recurse -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    return ($newest -and $newest.LastWriteTimeUtc -gt $built)
}

if ($Stop) {
    if (Test-Health) { Stop-Api; Write-Host 'LifeOS stopped.' } else { Write-Host 'LifeOS is not running.' }
    return
}

if ($Status) {
    if (Test-Health) { Write-Host "LifeOS is running: http://127.0.0.1:$Port" } else { Write-Host 'LifeOS is not running.' }
    $url = Get-TailscaleUrl
    if ($url) { Write-Host "Via Tailscale: $url" }
    return
}

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

# 1. Database, daily backup, schema.
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'devdb.ps1') start
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL did not start, see the message above.' }
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'backup.ps1') -IfOlderThanHours 20
Push-Location (Join-Path $Root 'backend')
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed, see the message above.' }
}
finally { Pop-Location }

# 2. Web client build.
if (Test-ClientOutdated) {
    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $npm) { $npm = Join-Path $env:ProgramFiles 'nodejs\npm.cmd' }
    Push-Location $webDir
    try {
        if (-not (Test-Path -LiteralPath (Join-Path $webDir 'node_modules'))) {
            & $npm install --no-fund --no-audit
            if ($LASTEXITCODE -ne 0) { throw 'npm install failed.' }
        }
        Write-Host 'Building the web client...'
        & $npm run build
        if ($LASTEXITCODE -ne 0) { throw 'The web client build failed.' }
    }
    finally { Pop-Location }
    # A running API keeps serving the old files list fine, but restart it to be safe.
    if (Test-Health) { Stop-Api }
}

# 3. API (hidden window, restarts are cheap).
if (Test-Health) {
    Write-Host "LifeOS is already running: http://127.0.0.1:$Port"
}
else {
    $command = "`$host.UI.RawUI.WindowTitle = 'LifeOS production'; " +
        "& '$python' -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $Port *> '$LogFile'"
    Start-Process powershell -WindowStyle Hidden -WorkingDirectory (Join-Path $Root 'backend') `
        -ArgumentList @('-NoProfile', '-Command', $command) | Out-Null
    $ready = $false
    for ($i = 0; $i -lt 60 -and -not $ready; $i++) {
        Start-Sleep -Milliseconds 500
        $ready = Test-Health
    }
    if (-not $ready) { throw "LifeOS did not start. See $LogFile" }
    Write-Host "LifeOS is running: http://127.0.0.1:$Port"
}

$url = Get-TailscaleUrl
if ($url) { Write-Host "Via Tailscale: $url" }
else { Write-Host 'Tailscale is not set up yet: see the Tailscale section of README.md.' }
