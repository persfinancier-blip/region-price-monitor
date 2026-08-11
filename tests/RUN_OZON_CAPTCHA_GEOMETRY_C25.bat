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
echo OZON CAPTCHA DOM GEOMETRY CALIBRATION C25
echo Fresh sticky -^> live challenge -^> local solver -^> hidden Chrome DOM geometry.
echo NO click. NO drag. NO pointer/mouse automation. NO challenge submission.
echo PASSWORD INPUT IS VISIBLE and is NOT persisted.
echo ============================================================
echo.

echo [1/2] Deterministic C25 tests ...
"%PY%" tests\test_wave2_ozon_captcha_geometry_c25.py -v
if errorlevel 1 (
  echo [ERROR] C25_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live solver-to-DOM geometry calibration ...
"%PY%" tools\probe_ozon_captcha_geometry_c25.py
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C25 completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_captcha_geometry_c25_report.json
echo Screenshot: parser\core\local\probes\ozon_captcha_geometry_c25.png
pause
exit /b %RC%
