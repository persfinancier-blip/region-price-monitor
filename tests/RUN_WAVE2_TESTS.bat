@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist "parser\core\venv\Scripts\python.exe" (
  echo [ERROR] VENV_NOT_FOUND
  echo Run the normal parser launcher once first.
  pause
  exit /b 1
)

set "PYTHONPATH=%CD%\parser\core"
"parser\core\venv\Scripts\python.exe" -m unittest discover -s tests -p "test_wave2.py" -v
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo [PASS] WAVE2_DETERMINISTIC_TESTS
) else (
  echo [FAIL] WAVE2_DETERMINISTIC_TESTS code=%RC%
)
pause
exit /b %RC%
