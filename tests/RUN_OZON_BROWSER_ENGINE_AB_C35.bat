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
echo OZON BROWSER ENGINE A/B C35
echo Stock Playwright Firefox vs Camoufox on ONE sticky/IP.
echo Observation only. No CAPTCHA interaction/submission.
echo ============================================================
echo.

echo [1/3] Deterministic C35 tests ...
"%PY%" tests\test_wave2_ozon_browser_engine_ab_c35.py -v
if errorlevel 1 (
  echo [ERROR] C35_DETERMINISTIC_TESTS_FAILED
  pause
  exit /b 3
)

echo.
echo [2/3] Ensuring official Playwright Firefox is installed ...
"%PY%" -m playwright install firefox
if errorlevel 1 (
  echo [ERROR] C35_PLAYWRIGHT_FIREFOX_INSTALL_FAILED
  pause
  exit /b 4
)

echo.
echo [3/3] Live A/B comparison on one sticky session ...
"%PY%" tools\probe_ozon_browser_engine_ab_c35.py %*
set "RC=%ERRORLEVEL%"

echo.
echo [INFO] Ozon C35 completed code=%RC%
pause
exit /b %RC%
