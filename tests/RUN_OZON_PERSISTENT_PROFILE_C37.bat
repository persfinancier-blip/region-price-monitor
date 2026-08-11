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

echo [1/2] Deterministic C37 tests ...
"%PY%" tests\test_wave2_ozon_persistent_profile_c37.py -v
if errorlevel 1 (
  echo [ERROR] C37_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live persistent-profile comparison ...
"%PY%" tools\probe_ozon_persistent_profile_c37.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C37 completed code=%RC%
pause
exit /b %RC%
