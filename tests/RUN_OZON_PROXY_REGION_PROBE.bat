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
"parser\core\venv\Scripts\python.exe" tools\probe_ozon_proxy_region_effect.py
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon proxy-region probe completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_proxy_region_effect_report.json
pause
exit /b %RC%
