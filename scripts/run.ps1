# checkPLC start Web server
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: .venv not found. Run setup.bat first." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$HostAddr = "127.0.0.1"
$Port = 8000
$Url = "http://${HostAddr}:${Port}"

Write-Host ""
Write-Host "checkPLC starting ..." -ForegroundColor Cyan
Write-Host "URL: $Url" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

Start-Process $Url -ErrorAction SilentlyContinue

& $venvPython -m uvicorn web.app.main:app --host $HostAddr --port $Port
