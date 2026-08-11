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
echo OZON SESSION QUALITY C30
echo Fresh sticky sessions -> same Camoufox -> cookie/API quality.
echo Cached local proxy is used automatically.
echo ============================================================
echo.

echo [1/2] Deterministic C30 tests ...
"%PY%" tests\test_wave2_ozon_session_quality_c30.py -v
if errorlevel 1 (
  echo [ERROR] C30_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live session quality probe ...
"%PY%" tools\probe_ozon_session_quality_c30.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C30 completed code=%RC%
pause
exit /b %RC%
