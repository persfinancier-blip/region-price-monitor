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
echo OZON LOCAL CHALLENGE / SOLVER TEST C20
echo Clean-room local image solver + live challenge fingerprint.
echo NO browser. NO external CAPTCHA solver API.
echo Proxy input will be VISIBLE. Credentials are NOT persisted.
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

echo [1/3] Deterministic local slider tests ...
"%PY%" tests\test_wave2_local_slider_solver.py
if errorlevel 1 (
  echo [ERROR] C20_LOCAL_SLIDER_TESTS_FAILED
  pause
  exit /b 3
)

echo [2/3] Deterministic challenge-safety tests ...
"%PY%" tests\test_wave2_ozon_challenge_c20.py
if errorlevel 1 (
  echo [ERROR] C20_CHALLENGE_SAFETY_TESTS_FAILED
  pause
  exit /b 4
)

echo.
echo [3/3] Live Ozon challenge capture/fingerprint ...
"%PY%" tools\probe_ozon_challenge_c20.py
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C20 completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_challenge_c20_report.json
echo Raw challenge/assets: parser\core\local\probes\ozon_challenge_c20\
pause
exit /b %RC%
