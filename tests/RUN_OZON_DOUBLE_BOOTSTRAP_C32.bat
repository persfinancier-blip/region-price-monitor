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
echo OZON DOUBLE BOOTSTRAP C32
echo One sticky: HEADLESS first, then VISIBLE on same sticky/IP.
echo Cached local proxy is used automatically.
echo ============================================================
echo.

echo [1/2] Deterministic C32 tests ...
"%PY%" tests\test_wave2_ozon_double_bootstrap_c32.py -v
if errorlevel 1 (
  echo [ERROR] C32_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live double-bootstrap probe ...
"%PY%" tools\probe_ozon_double_bootstrap_c32.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C32 completed code=%RC%
pause
exit /b %RC%
