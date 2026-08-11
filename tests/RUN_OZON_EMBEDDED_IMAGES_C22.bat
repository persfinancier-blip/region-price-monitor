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
echo OZON EMBEDDED CHALLENGE IMAGE SOLVER C22
echo C19 payload -^> exact PNGs -^> SAME sticky proxy -^> local solver.
echo NO browser. NO external solver API. NO challenge submission.
echo PASSWORD INPUT IS VISIBLE and is NOT persisted.
echo ============================================================
echo.

echo [1/2] Deterministic payload tests ...
"%PY%" tests\test_wave2_ozon_payload_c22.py -v
if errorlevel 1 (
  echo [ERROR] C22_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/2] Live exact embedded-image solve ...
"%PY%" tools\probe_ozon_embedded_images_c22.py
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C22 completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_payload_c22_report.json
echo Raw images: parser\core\local\probes\ozon_payload_c22\
pause
exit /b %RC%
