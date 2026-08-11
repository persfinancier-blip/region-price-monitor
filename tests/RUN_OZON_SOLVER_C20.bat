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
echo OZON C20 REAL LOCAL SOLVER EVALUATION
echo Uses ONLY already captured local C20 files.
echo NO network. NO browser. NO CAPTCHA submission.
echo ============================================================
echo.

"%PY%" -c "import numpy; from PIL import Image" >nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing local image dependencies numpy + Pillow ...
  "%PY%" -m pip install "numpy>=1.24.0" "Pillow>=10.0.0"
  if errorlevel 1 (
    echo [ERROR] IMAGE_DEPENDENCY_INSTALL_FAILED
    pause
    exit /b 2
  )
)

if not exist "parser\core\local\probes\ozon_challenge_c20" (
  echo [ERROR] C20_CAPTURE_NOT_FOUND
  echo First run tests\RUN_OZON_CHALLENGE_C20.bat and complete the challenge capture.
  pause
  exit /b 3
)

"%PY%" tools\evaluate_ozon_solver_c20.py
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Solver evaluation completed code=%RC%
echo Report: parser\core\local\probes\ozon_solver_c20_eval_report.json
echo Preview if solved: parser\core\local\probes\ozon_solver_c20_preview.png
echo.
if "%RC%"=="0" (
  echo [PASS] A real local solver candidate was produced.
) else (
  echo [INFO] No accepted real solve yet. Read the EVIDENCE gate above.
)
pause
exit /b %RC%
