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
echo OZON LIVE SOLVER ROBUSTNESS C24
echo 3 fresh sticky sessions -^> 3 live challenges -^> local solver.
echo Saves local preview PNG for each successful solve.
echo NO CAPTCHA submission. NO browser. NO external solver API.
echo PASSWORD INPUT IS VISIBLE and is NOT persisted.
echo ============================================================
echo.

echo [1/2] Deterministic C24 tests ...
"%PY%" tests\test_wave2_ozon_solver_robustness_c24.py -v
if errorlevel 1 (
  echo [ERROR] C24_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live 3-sample robustness run ...
"%PY%" tools\probe_ozon_solver_robustness_c24.py --runs 3
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C24 completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_solver_robustness_c24_report.json
echo Raw + preview evidence: parser\core\local\probes\ozon_solver_robustness_c24\run_XX\
pause
exit /b %RC%
