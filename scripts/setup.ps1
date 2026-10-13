<#
.SYNOPSIS
  One-time setup of OpenID Vision on Windows 10/11.

.DESCRIPTION
  Creates the Python virtual environment, installs the backend packages (CPU PyTorch), writes your .env
  (access keys are off by default - nothing to type), downloads and verifies the model weights, installs Node.js locally if you
  have none, and builds the web interface.

  Everything that is cached or temporary is kept INSIDE this project (the .tools folder), so nothing is
  written to the system drive. That matters on machines whose C: drive is nearly full.

.PARAMETER SkipNode     Do not set up Node.js / the frontend (backend only).
.PARAMETER SkipWeights  Do not download model weights (do it later with scripts\download_weights.py).
.PARAMETER DryRun       Print what would be done without doing it.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>
param(
    [switch]$SkipNode,
    [switch]$SkipWeights,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root ".tools"
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"

# Keep caches and temp files on the project drive.
foreach ($folder in "tmp", "pip-cache", "npm-cache") { New-Item -ItemType Directory -Force (Join-Path $Tools $folder) | Out-Null }
$env:TEMP = Join-Path $Tools "tmp"
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $Tools "pip-cache"
$env:npm_config_cache = Join-Path $Tools "npm-cache"
$env:npm_config_update_notifier = "false"

function Step([string]$text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }

function Run([string]$exe, [string[]]$arguments) {
    if ($DryRun) { Write-Host "[dry run] $exe $($arguments -join ' ')"; return }
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $exe $($arguments -join ' ')" }
}

# ---------------------------------------------------------------- 1. Python
Step "Checking Python (3.11 or newer)"
$python = $null
foreach ($candidate in @("python", "py")) {
    $found = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($found) { $python = $found.Source; break }
}
if (-not $python) { throw "Python was not found. Install Python 3.11+ from https://www.python.org/downloads/ and run this script again." }
$ok = & $python -c "import sys; print(sys.version_info >= (3, 11))"
if ($ok -ne "True") { throw "Python 3.11 or newer is required (found: $(& $python --version))." }
Write-Host (& $python --version)

# ---------------------------------------------------------------- 2. Backend packages
Step "Creating the virtual environment and installing backend packages (this downloads about 300 MB)"
if (-not (Test-Path $VenvPython) -or $DryRun) { Run $python @("-m", "venv", (Join-Path $Backend ".venv")) }
Run $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
Run $VenvPython @("-m", "pip", "install", "torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cpu")
Run $VenvPython @("-m", "pip", "install", "-r", (Join-Path $Backend "requirements-dev.txt"))

# ---------------------------------------------------------------- 3. Configuration
Step "Creating .env (skipped if it already exists)"
Run $VenvPython @((Join-Path $Root "scripts\init_env.py"))

# ---------------------------------------------------------------- 4. Weights
if (-not $SkipWeights) {
    Step "Downloading and verifying model weights (OSNet about 9 MB, detector about 75 MB)"
    Run $VenvPython @((Join-Path $Root "scripts\download_weights.py"))
}

# ---------------------------------------------------------------- 5. Node + frontend
if (-not $SkipNode) {
    Step "Checking Node.js (20 or newer)"
    $node = Get-Command node -ErrorAction SilentlyContinue
    $nodeDir = $null
    if ($node) {
        $major = [int]((& node --version).TrimStart("v").Split(".")[0])
        if ($major -ge 20) { $nodeDir = Split-Path -Parent $node.Source; Write-Host "Using Node $(& node --version) from $nodeDir" }
    }
    if (-not $nodeDir) {
        $local = Get-ChildItem $Tools -Directory -Filter "node-v*-win-x64" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($local) { $nodeDir = $local.FullName; Write-Host "Using the local Node.js in $nodeDir" }
    }
    if (-not $nodeDir) {
        Step "Installing a portable Node.js LTS into .tools (official nodejs.org build, checksum verified)"
        if ($DryRun) {
            Write-Host "[dry run] download node-v<LTS>-win-x64.zip from nodejs.org, verify SHA-256 against SHASUMS256.txt, extract to .tools"
        } else {
            $index = Invoke-RestMethod "https://nodejs.org/dist/index.json"
            $version = ($index | Where-Object { $_.lts } | Select-Object -First 1).version
            $zip = Join-Path $Tools "_node-$version.zip"
            Invoke-WebRequest "https://nodejs.org/dist/$version/node-$version-win-x64.zip" -OutFile $zip -UseBasicParsing
            $sums = (Invoke-WebRequest "https://nodejs.org/dist/$version/SHASUMS256.txt" -UseBasicParsing).Content
            $expected = (($sums -split "`n") | Where-Object { $_ -match "node-$version-win-x64.zip$" }) -replace "\s+.*", ""
            $actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
            if ($expected -ne $actual) { Remove-Item $zip -Force; throw "Node.js download failed its SHA-256 check - nothing was installed." }
            Expand-Archive $zip -DestinationPath $Tools -Force
            Remove-Item $zip -Force
            $nodeDir = Join-Path $Tools "node-$version-win-x64"
            Write-Host "Installed Node $version (checksum verified) in $nodeDir"
        }
    }
    if ($nodeDir) { $env:PATH = "$nodeDir;$env:PATH" }

    Step "Installing frontend packages and building the interface"
    Push-Location $Frontend
    try {
        Run "npm" @("install", "--no-audit", "--no-fund")
        Run "npm" @("run", "build")
    } finally { Pop-Location }
}

Step "Setup finished"
Write-Host "Next:  powershell -File scripts\start.ps1        (then open http://127.0.0.1:8000)"
Write-Host "No access key is needed (REID_AUTH_REQUIRED=false in .env). Set it to true to require keys."
if (-not (Test-Path (Join-Path $Root "datasets\market1501"))) {
    Write-Host "For real benchmark numbers, add Market-1501 (research use): see README, 'Dataset acquisition'."
}
