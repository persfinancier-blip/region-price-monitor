@echo off
setlocal
cd /d "%~dp0.."
set "PYTHONPATH=%CD%\parser\core;%CD%\tools"
"parser\core\venv\Scripts\python.exe" tools\probe_ozon_same_sticky_direct_c19.py
set "RC=%ERRORLEVEL%"
echo.
echo C19 completed code=%RC%
echo Safe report: parser\core\local\probes\ozon_same_sticky_direct_c19_report.json
pause
exit /b %RC%
