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

"%PY%" tests\test_ozon_captcha_split_scripts.py -v
if errorlevel 1 (
  echo [ERROR] SPLIT_SCRIPT_TESTS_FAILED
  pause
  exit /b 3
)

echo.
"%PY%" tools\ozon_captcha_human_handoff_price.py
set "RC=%ERRORLEVEL%"
echo.
echo [INFO] Human handoff completed code=%RC%
pause
exit /b %RC%
