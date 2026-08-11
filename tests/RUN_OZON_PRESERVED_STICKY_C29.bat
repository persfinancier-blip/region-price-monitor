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
echo OZON PRESERVED STICKY C29
echo Reuse exact cached hold-session-session-id. NO rotation.
echo ============================================================
echo.

echo [1/2] Deterministic C29 tests ...
"%PY%" tests\test_wave2_ozon_preserved_sticky_c29.py -v
if errorlevel 1 (
  echo [ERROR] C29_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live preserved-sticky probe ...
"%PY%" tools\probe_ozon_preserved_sticky_c29.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C29 completed code=%RC%
pause
exit /b %RC%
