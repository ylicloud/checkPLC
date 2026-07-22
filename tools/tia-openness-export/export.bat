@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if "%TIA_PUBLICAPI%"=="" set "TIA_PUBLICAPI=C:\Program Files\Siemens\Automation\Portal V20\PublicAPI\V20"

echo Building CheckPlc.TiaExport ...
dotnet build -c Release
if errorlevel 1 (
  echo Build failed. Check TIA_PUBLICAPI=%TIA_PUBLICAPI%
  exit /b 1
)

set "EXE=%~dp0bin\Release\net48\CheckPlc.TiaExport.exe"
if not exist "%EXE%" (
  echo EXE not found: %EXE%
  exit /b 1
)

echo.
echo Running export...
"%EXE%" %*
exit /b %ERRORLEVEL%
