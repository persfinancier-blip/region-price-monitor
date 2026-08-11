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
echo OZON ASSEMBLED PRICE READER C26
echo SG04 proxy-first -^> PRICE/CHALLENGE.
echo SG05 authenticated fallback only by EXPLICIT operator choice.
echo NO CAPTCHA submission. NO automatic fallback.
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
echo [2/2] Live assembled price-reader test ...
"%PY%" tools\probe_ozon_price_reader_c26.py
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C26 completed code=%RC%
pause
exit /b %RC%
