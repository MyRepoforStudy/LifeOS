<#
.SYNOPSIS
    Back up the LifeOS database (pg_dump, custom format) and keep the newest copies.

        powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1
        powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -IfOlderThanHours 20   # used by prod.ps1

    Backups go to Documents\LifeOS-backups. Restore one (this replaces current data):
        $env:PGPASSWORD = '<LIFEOS_DB_PASSWORD from backend\.env>'
        & 'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe' -h localhost -U lifeos -d lifeos --clean --if-exists <file>
#>
param(
    [int]$IfOlderThanHours = 0,
    [int]$Keep = 14
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root 'backend\.env'
$PgBin = if ($env:PG_BIN) { $env:PG_BIN } else { 'C:\Program Files\PostgreSQL\18\bin' }
$BackupDir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'LifeOS-backups'

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$existing = Get-ChildItem -LiteralPath $BackupDir -Filter 'lifeos-*.dump' | Sort-Object LastWriteTime -Descending

if ($IfOlderThanHours -gt 0 -and $existing -and $existing[0].LastWriteTime -gt (Get-Date).AddHours(-$IfOlderThanHours)) {
    Write-Host "Latest backup is recent: $($existing[0].Name)"
    return
}

$password = $null
foreach ($line in Get-Content -LiteralPath $EnvFile) {
    if ($line -match '^\s*LIFEOS_DB_PASSWORD\s*=\s*(.*)$') { $password = $Matches[1].Trim() }
}
if (-not $password) { throw "LIFEOS_DB_PASSWORD not found in $EnvFile" }

$target = Join-Path $BackupDir ('lifeos-{0}.dump' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
$env:PGPASSWORD = $password
try {
    & (Join-Path $PgBin 'pg_dump.exe') -h localhost -U lifeos -d lifeos --format=custom --file $target
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}
Write-Host "Backup written: $target"

Get-ChildItem -LiteralPath $BackupDir -Filter 'lifeos-*.dump' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Keep | Remove-Item -Force
