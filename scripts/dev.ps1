<#
.SYNOPSIS
    Start LifeOS for local development: PostgreSQL, migrations, API and web client.

        powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1         # on this computer
        powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Lan    # also reachable from a phone on the same Wi-Fi

    The API and the web client open in two new PowerShell windows ("LifeOS API" and
    "LifeOS Web"); close a window to stop that server. PostgreSQL keeps running in the
    background: stop it with scripts\devdb.ps1 stop.
#>
param([switch]$Lan)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

# A terminal opened before Node.js, Python or Git were installed still has the old
# PATH. Reload it from the registry so this script and the windows it opens see them.
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')

function Test-Port([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Start-Window([string]$Title, [string]$Directory, [string]$Command) {
    $script = "`$host.UI.RawUI.WindowTitle = '$Title'; $Command"
    Start-Process powershell -WorkingDirectory $Directory -ArgumentList @('-NoExit', '-NoProfile', '-Command', $script) | Out-Null
}

$python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend virtualenv not found ($python). Create it as described in README.md (Windows setup, step 2)."
}

$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npm) { $npm = Join-Path $env:ProgramFiles 'nodejs\npm.cmd' }
if (-not (Test-Path -LiteralPath $npm)) {
    throw 'npm.cmd not found. Install Node.js LTS: winget install --id OpenJS.NodeJS.LTS -e'
}

# 1. Database (creates nothing: run scripts\devdb.ps1 init once before the first start).
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'devdb.ps1') start
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL did not start, see the message above.' }

# 2. Database schema.
Push-Location (Join-Path $Root 'backend')
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed, see the message above.' }
}
finally {
    Pop-Location
}

# 3. Web client dependencies (first run only).
if (-not (Test-Path -LiteralPath (Join-Path $Root 'web\node_modules'))) {
    Push-Location (Join-Path $Root 'web')
    try {
        & $npm install --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) { throw 'npm install failed, see the message above.' }
    }
    finally {
        Pop-Location
    }
}

# 4. API on http://127.0.0.1:8000
if (Test-Port 8000) {
    Write-Host 'Port 8000 is already in use: the API seems to be running (or another program uses the port).'
}
else {
    Start-Window 'LifeOS API' (Join-Path $Root 'backend') "& '$python' -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload"
}

# 5. Web client on http://localhost:5173 (it forwards /api to the API).
if (Test-Port 5173) {
    Write-Host 'Port 5173 is already in use: the web client seems to be running.'
}
else {
    $task = if ($Lan) { 'dev:lan' } else { 'dev' }
    Start-Window 'LifeOS Web' (Join-Path $Root 'web') "& '$npm' run $task"
}

Write-Host ''
Write-Host 'LifeOS is starting. Open http://localhost:5173 in a few seconds.'
if ($Lan) {
    $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        Select-Object -ExpandProperty IPAddress
    foreach ($address in $addresses) { Write-Host "From the phone (same Wi-Fi): http://${address}:5173" }
}
