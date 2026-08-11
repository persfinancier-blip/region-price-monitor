@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist "parser\core\venv\Scripts\python.exe" (
  echo [ERROR] VENV_NOT_FOUND
  pause
  exit /b 1
)

set "PY=parser\core\venv\Scripts\python.exe"
set "PYTHONPATH=%CD%\parser\core;%CD%\tools"

echo ============================================================
echo BROWSER TLS / PROXY SECURITY C33
echo Neutral HTTPS + Ozon HTTPS navigation security only.
echo No CAPTCHA interaction. No price request.
echo ============================================================
echo.

echo [1/2] Deterministic C33 tests ...
"%PY%" tests\test_wave2_browser_tls_proxy_c33.py -v
if errorlevel 1 (
  echo [ERROR] C33_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live TLS/proxy security preflight ...
"%PY%" tools\probe_browser_tls_proxy_c33.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Browser TLS C33 completed code=%RC%
pause
exit /b %RC%
