@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist "parser\core\venv\Scripts\python.exe" (
  echo [ERROR] VENV_NOT_FOUND
  echo Run the normal parser launcher once first.
  pause
  exit /b 1
)

echo ============================================================
echo CLAUDE MOBILE PROXY TEST C18
echo Exact selector: rotate sticky session, curl_cffi IP/operator.
echo PASSWORD INPUT IS VISIBLE. It is NOT saved to SAFE REPORT.
echo Input format: host:port:user:pass
echo ============================================================
echo.

set "PYTHONPATH=%CD%\parser\core;%CD%\tools"
"parser\core\venv\Scripts\python.exe" tools\mobile_proxy.py --tries 15
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C18 exact Claude sticky mobile selector completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_mobile_proxy_selector_report.json
pause
exit /b %RC%
