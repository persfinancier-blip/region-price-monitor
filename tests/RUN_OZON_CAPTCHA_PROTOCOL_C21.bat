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
echo OZON CAPTCHA PROTOCOL C21
echo LOCAL ONLY. NO network. NO browser. NO submission.
echo ============================================================
echo.

"%PY%" tests\test_wave2_ozon_captcha_protocol_c21.py -v
if errorlevel 1 (
  echo [ERROR] C21_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

"%PY%" tools\analyze_ozon_captcha_protocol_c21.py
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C21 completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_captcha_protocol_c21_report.json
pause
exit /b %RC%
