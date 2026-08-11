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
"parser\core\venv\Scripts\python.exe" tools\probe_ozon_zero_human_bootstrap.py
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo [PASS] OZON_ZERO_HUMAN_BOOTSTRAP_AND_ENTRYPOINT_PROVEN
) else (
  echo [EVIDENCE] OZON_ZERO_HUMAN_BOOTSTRAP_NOT_YET_PROVEN code=%RC%
)
echo Safe report: parser\core\local\probes\ozon_zero_human_bootstrap_report.json
pause
exit /b %RC%
