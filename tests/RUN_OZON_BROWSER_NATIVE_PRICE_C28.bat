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
echo OZON BROWSER-NATIVE PRICE C28
echo One Camoufox + one sticky proxy + browser-native API fetch.
echo No curl handoff. Same browser network stack end-to-end.
echo ============================================================
echo.

echo [1/2] Deterministic C28 tests ...
"%PY%" tests\test_wave2_ozon_browser_native_price_c28.py -v
if errorlevel 1 (
  echo [ERROR] C28_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live browser-native price probe ...
"%PY%" tools\probe_ozon_browser_native_price_c28.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C28 completed code=%RC%
pause
exit /b %RC%
