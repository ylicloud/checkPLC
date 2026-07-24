@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if "%TIA_PUBLICAPI%"=="" (
  if exist "C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Base.dll" (
    set "TIA_PUBLICAPI=C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48"
  ) else if exist "C:\Program Files\Siemens\Automation\Portal V20\PublicAPI\V20\Siemens.Engineering.dll" (
    set "TIA_PUBLICAPI=C:\Program Files\Siemens\Automation\Portal V20\PublicAPI\V20"
  ) else (
    set "TIA_PUBLICAPI=C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48"
  )
)

echo TIA_PUBLICAPI=%TIA_PUBLICAPI%
echo Building CheckPlc.TiaExport ...
dotnet build -c Release -p:TiaPublicApi="%TIA_PUBLICAPI%"
if errorlevel 1 (
  echo Build failed. Check TIA_PUBLICAPI=%TIA_PUBLICAPI%
  exit /b 1
)

set "EXE=%~dp0bin\Release\net48\CheckPlc.TiaExport.exe"
if not exist "%EXE%" (
  echo EXE not found: %EXE%
  exit /b 1
)

rem V21 运行时还依赖 Bin\PublicAPI 下的 Contract 等程序集
set "TIA_BIN_PUBLICAPI=C:\Program Files\Siemens\Automation\Portal V21\Bin\PublicAPI"
set "TIA_BIN=C:\Program Files\Siemens\Automation\Portal V21\Bin"
if exist "%TIA_BIN_PUBLICAPI%\Siemens.Engineering.Contract.dll" (
  set "PATH=%TIA_PUBLICAPI%;%TIA_BIN_PUBLICAPI%;%TIA_BIN%;%PATH%"
) else (
  set "PATH=%TIA_PUBLICAPI%;%PATH%"
)

echo.
echo Running export...
"%EXE%" %*
exit /b %ERRORLEVEL%
