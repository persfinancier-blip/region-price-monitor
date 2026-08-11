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
"parser\core\venv\Scripts\python.exe" tools\probe_server_visibility.py
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo [PASS] SERVER_SEES_WB_AND_OZON
  echo Safe report: parser\core\local\probes\server_visibility_report.json
) else (
  echo [FAIL] SERVER_MARKETPLACE_VISIBILITY code=%RC%
  echo Safe report: parser\core\local\probes\server_visibility_report.json
)
pause
exit /b %RC%
