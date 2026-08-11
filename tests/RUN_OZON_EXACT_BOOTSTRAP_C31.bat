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
echo OZON EXACT SUCCESSFUL-BOOTSTRAP REPRODUCTION C31
echo Ozon first navigation. 30s API wait. One HOME retry on timeout.
echo Cached local proxy. No CAPTCHA interaction/submission.
echo ============================================================
echo.

echo [1/2] Deterministic C31 tests ...
"%PY%" tests\test_wave2_ozon_exact_bootstrap_c31.py -v
if errorlevel 1 (
  echo [ERROR] C31_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live exact-bootstrap reproduction ...
"%PY%" tools\probe_ozon_exact_bootstrap_c31.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C31 completed code=%RC%
pause
exit /b %RC%
