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
"parser\core\venv\Scripts\python.exe" tools\probe_wave2_live.py
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo [INFO] WAVE2_LIVE_PROBE_FINISHED
  echo Send the SAFE REPORT output or parser\core\local\probes\wave2_probe_report.json to the developer.
) else (
  echo [FAIL] WAVE2_LIVE_PROBE code=%RC%
)
pause
exit /b %RC%
