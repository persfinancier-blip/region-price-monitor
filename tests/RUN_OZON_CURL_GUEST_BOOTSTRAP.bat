@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist "parser\core\venv\Scripts\python.exe" (
  echo [ERROR] VENV_NOT_FOUND
  echo Run the normal parser launcher once first.
  pause
  exit /b 1
)

set "PYTHONPATH=%CD%\parser\core"
"parser\core\venv\Scripts\python.exe" tools\probe_ozon_curl_guest_bootstrap.py
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C12 curl guest bootstrap completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_curl_guest_bootstrap_report.json
pause
exit /b %RC%
