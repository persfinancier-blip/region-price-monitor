@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist "parser\core\venv\Scripts\python.exe" (
  echo [ERROR] VENV_NOT_FOUND
  echo Run the normal parser launcher once first.
  pause
  exit /b 1
)

set "PY=parser\core\venv\Scripts\python.exe"
set "PYTHONPATH=%CD%\parser\core;%CD%\tools"

echo ============================================================
echo OZON SINGLE-RUN MOBILE CHALLENGE SOLVER C23
echo Fresh sticky -^> live challenge -^> images -^> local solver.
echo ONE PROCESS. NO historical C18/C19 IP dependency.
echo NO browser. NO external solver API. NO challenge submission.
echo Proxy/password input is VISIBLE and is NOT persisted.
echo ============================================================
echo.

echo [1/2] Deterministic C23 tests ...
"%PY%" tests\test_wave2_ozon_single_run_c23.py -v
if errorlevel 1 (
  echo [ERROR] C23_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live one-process challenge/image/solver test ...
"%PY%" tools\probe_ozon_single_run_c23.py
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C23 completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_single_run_c23_report.json
echo Raw local evidence: parser\core\local\probes\ozon_single_run_c23\
pause
exit /b %RC%
