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
echo OZON SESSION COHERENCE C27
echo one sticky proxy ^| all browser cookies ^| same browser family
echo ============================================================
echo.

echo [1/2] Deterministic C27 tests ...
"%PY%" tests\test_wave2_ozon_session_coherence_c27.py -v
if errorlevel 1 (
  echo [ERROR] C27_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live coherent-session probe ...
"%PY%" tools\probe_ozon_session_coherence_c27.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C27 completed code=%RC%
pause
exit /b %RC%
