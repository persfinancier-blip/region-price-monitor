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
echo OZON STOCK FIREFOX DIRECT VS MOBILE PROXY C36
echo Same browser code. Arm A direct, Arm B through cached proxy.
echo No CAPTCHA interaction/submission.
echo ============================================================
echo.

echo [1/2] Deterministic C36 tests ...
"%PY%" tests\test_wave2_ozon_direct_vs_proxy_c36.py -v
if errorlevel 1 (
  echo [ERROR] C36_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live direct-vs-proxy comparison ...
"%PY%" tools\probe_ozon_direct_vs_proxy_c36.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C36 completed code=%RC%
pause
exit /b %RC%
