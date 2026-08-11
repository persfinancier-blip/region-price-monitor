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
echo OZON SECURITY UI / MIXED CONTENT C34
echo C33-proven HTTPS proxy. Diagnose visible Not Secure label.
echo No price request. No CAPTCHA interaction/submission.
echo ============================================================
echo.

echo [1/2] Deterministic C34 tests ...
"%PY%" tests\test_wave2_ozon_security_ui_c34.py -v
if errorlevel 1 (
  echo [ERROR] C34_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live browser security UI diagnostic ...
"%PY%" tools\probe_ozon_security_ui_c34.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C34 completed code=%RC%
pause
exit /b %RC%
