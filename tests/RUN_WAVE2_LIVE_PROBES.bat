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
"parser\core\venv\Scripts\python.exe" tools\probe_wb_current_endpoint.py
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo [PASS] WB_CURRENT_ENDPOINT_DATA_ACCESS_PROVEN
  echo Safe report: parser\core\local\probes\wb_current_endpoint_report.json
) else (
  echo [EVIDENCE] WB_CURRENT_ENDPOINT_NOT_YET_PROVEN code=%RC%
  echo Safe report: parser\core\local\probes\wb_current_endpoint_report.json
)
pause
exit /b %RC%
