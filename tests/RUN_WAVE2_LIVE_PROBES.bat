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
"parser\core\venv\Scripts\python.exe" tools\probe_browser_visibility.py
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo [PASS] VISIBLE_BROWSER_SMOKE_FINISHED
  echo Tell the developer what you saw on the WB and Ozon tabs.
  echo Safe report: parser\core\local\probes\browser_visibility_report.json
) else (
  echo [FAIL] VISIBLE_BROWSER_SMOKE code=%RC%
  echo Safe report: parser\core\local\probes\browser_visibility_report.json
)
pause
exit /b %RC%
