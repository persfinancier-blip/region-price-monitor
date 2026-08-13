@echo off
REM ASCII-only by design: Windows CMD breaks on non-ASCII in .bat files.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo === Wildberries regional prices ===
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from python.org
    echo         and tick "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating local venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] venv creation failed
        pause
        exit /b 1
    )
) else (
    echo [1/3] venv already exists
)

echo [2/3] Installing dependencies ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet requests
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)

echo [3/3] Running ...
echo.
REM No arguments = Moscow + Novosibirsk + Vladivostok from sku.csv, CSV into results\
if "%~1"=="" (
    ".venv\Scripts\python.exe" wb_price.py --city msk --city nvs --city vvo --sku-file sku.csv --csv results
) else (
    ".venv\Scripts\python.exe" wb_price.py %*
)

echo.
pause
