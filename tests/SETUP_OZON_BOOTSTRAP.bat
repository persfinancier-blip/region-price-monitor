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
echo [INFO] Installing Playwright Python package into parser venv...
"%PY%" -m pip install "playwright>=1.40"
if errorlevel 1 goto :fail

echo [INFO] Installing Playwright Chromium runtime...
"%PY%" -m playwright install chromium
if errorlevel 1 goto :fail

echo [PASS] OZON_BOOTSTRAP_PLAYWRIGHT_READY
pause
exit /b 0

:fail
echo [FAIL] OZON_BOOTSTRAP_PLAYWRIGHT_SETUP
pause
exit /b 1
