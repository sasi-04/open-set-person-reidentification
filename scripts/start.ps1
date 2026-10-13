<#
.SYNOPSIS
  Start OpenID Vision.

.DESCRIPTION
  Default: starts the backend on http://127.0.0.1:8000, which also serves the built web interface
  (run scripts\setup.ps1 once first). Press Ctrl+C to stop.

  With -Dev it also opens a second window running the Vite development server on http://localhost:5173
  (hot reload while you edit the frontend; it forwards /api calls to the backend).

.PARAMETER Port  Backend port (default 8000). If something else already uses it the script stops with a message - pick another with -Port.
.PARAMETER Dev   Also start the frontend development server.
#>
param(
    [int]$Port = 8000,
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root ".tools"
$Backend = Join-Path $Root "backend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) { throw "The virtual environment is missing. Run: powershell -File scripts\setup.ps1" }
if (-not (Test-Path (Join-Path $Root ".env"))) { Write-Warning "No .env found - the built-in defaults will be used. To create one: python scripts\init_env.py" }

New-Item -ItemType Directory -Force (Join-Path $Tools "tmp") | Out-Null
$env:TEMP = Join-Path $Tools "tmp"
$env:TMP = $env:TEMP

# Refuse to start if something else already owns the port (never kill someone else's process).
$inUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($inUse) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($inUse[0].OwningProcess)" -ErrorAction SilentlyContinue
    throw "Port $Port is already in use by: $($owner.CommandLine). Choose another port with -Port, or stop that program yourself."
}

if ($Dev) {
    $nodeDir = (Get-ChildItem $Tools -Directory -Filter "node-v*-win-x64" -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
    $pathPrefix = if ($nodeDir) { "`$env:PATH = '$nodeDir;' + `$env:PATH; " } else { "" }
    $cmd = "$pathPrefix`$env:REID_BACKEND_URL = 'http://127.0.0.1:$Port'; `$env:npm_config_cache = '$(Join-Path $Tools 'npm-cache')'; Set-Location '$(Join-Path $Root 'frontend')'; npm run dev"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd | Out-Null
    Write-Host "Frontend dev server starting in a new window: http://localhost:5173"
}

Write-Host "Backend starting: http://127.0.0.1:$Port   (API docs: http://127.0.0.1:$Port/api/docs)"
Set-Location $Backend
# --limit-concurrency: refuse (HTTP 503) instead of piling up work when a small CPU is already busy.
# --timeout-keep-alive: close idle connections after 10 seconds.
& $VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port --limit-concurrency 32 --timeout-keep-alive 10
