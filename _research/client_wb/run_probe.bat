@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Проба эндпоинтов Wildberries
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo Python не найден в PATH. Открой окно, где python работает, и запусти:
    echo     python probe_wb_endpoints.py
    pause
    exit /b 1
)

python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo Ставлю requests...
    python -m pip install requests
)

python probe_wb_endpoints.py %*

echo.
echo Готово. Отчёт: probe_report.txt, сырые ответы: probe_raw\
pause
