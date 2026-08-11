@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist "parser\core\venv\Scripts\python.exe" (
  echo [ERROR] VENV_NOT_FOUND
  echo Run the normal parser launcher once first.
  pause
  exit /b 1
)

set "PYTHONPATH=%CD%\parser\core;%CD%\tools"
"parser\core\venv\Scripts\python.exe" tools\probe_ozon_direct_endpoint_c17.py
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C17 direct endpoint completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_direct_endpoint_c17_report.json
pause
exit /b %RC%
