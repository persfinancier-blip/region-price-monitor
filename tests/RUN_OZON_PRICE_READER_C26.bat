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
echo OZON PRICE NOW C26
echo Goal: print the real Ozon price for the requested SKU.
echo SG04 proxy-first is attempted first.
echo If SG04 returns challenge/no-price, this runner EXPLICITLY
echo authorizes the preserved SG05 authenticated legacy fallback.
echo NO CAPTCHA submission or pointer automation.
echo ============================================================
echo.

echo [1/2] Deterministic C26 tests ...
"%PY%" tests\test_wave2_ozon_price_reader_c26.py -v
if errorlevel 1 (
  echo [ERROR] C26_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live price run ...
"%PY%" tools\probe_ozon_price_reader_c26.py --legacy-on-challenge
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C26 completed code=%RC%
pause
exit /b %RC%
