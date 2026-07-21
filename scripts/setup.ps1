# checkPLC one-click setup (Windows)
# Usage: double-click setup.bat in repo root, or: .\scripts\setup.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step($msg, $color = "White") {
    Write-Host $msg -ForegroundColor $color
}

Write-Host ""
Write-Step "========================================" "Cyan"
Write-Step "  checkPLC setup" "Cyan"
Write-Step "========================================" "Cyan"
Write-Host ""

# 1. Check Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Step "ERROR: Python not found. Install Python 3.10+ from https://www.python.org/downloads/" "Red"
    Write-Step "       Check 'Add python.exe to PATH' during install." "Yellow"
    exit 1
}

$verText = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$parts = $verText.Split(".")
$major = [int]$parts[0]
$minor = [int]$parts[1]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    Write-Step "ERROR: Python 3.10+ required, found $verText" "Red"
    exit 1
}
Write-Step "OK   Python $verText" "Green"

# 2. Create venv
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Step "...  Creating virtual env .venv" "Yellow"
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Write-Step "OK   Virtual env .venv" "Green"

# 3. Install dependencies
Write-Step "...  Installing Python packages (1-3 min first time)" "Yellow"
& $venvPython -m pip install --upgrade pip -q
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Step "OK   Dependencies installed" "Green"

# 4. Verify snap7
Write-Step "...  Checking snap7" "Yellow"
$snap7Ok = & $venvPython -c "from snap7 import client; print('ok')" 2>$null
if ($snap7Ok -eq "ok") {
    Write-Step "OK   snap7 ready (real PLC supported)" "Green"
} else {
    Write-Step "WARN snap7 not ready; Mock mode still works" "Yellow"
}

# 5. Optional voice clips
Write-Host ""
$genVoice = Read-Host "Generate voice WAV clips? [y/N]"
if ($genVoice -match "^[yY]") {
    & $venvPython -m pip install edge-tts -q
    & $venvPython scripts/generate_wavs.py
}

Write-Host ""
Write-Step "========================================" "Green"
Write-Step "  Setup complete!" "Green"
Write-Step "========================================" "Green"
Write-Host ""
Write-Step "Next: double-click run.bat, or run .\scripts\run.ps1" "Cyan"
Write-Step "Open: http://127.0.0.1:8000" "Cyan"
Write-Host ""
