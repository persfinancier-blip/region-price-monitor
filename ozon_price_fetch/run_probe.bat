@echo off
REM ASCII-only by design: Windows CMD breaks on non-ASCII in .bat files.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo === Ozon price probe ===
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

echo [2/3] Installing dependencies ^(first run only, may take a minute^) ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet curl-cffi drissionpage "camoufox[geoip]"
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)

REM Camoufox ships its own Firefox build; fetch it once (~100 MB).
if not exist ".venv\camoufox_fetched.flag" (
    echo       Downloading Camoufox browser, one time only ...
    ".venv\Scripts\python.exe" -m camoufox fetch
    if errorlevel 1 (
        echo [WARN] Camoufox browser download failed - will fall back to DrissionPage
    ) else (
        echo done > ".venv\camoufox_fetched.flag"
    )
)

echo [3/3] Running probe ...
echo.
REM No arguments = camoufox + real browser window + proxy from proxy.txt.
REM Real window is the Windows equivalent of the reference setup (Linux + Xvfb).
if "%~1"=="" (
    ".venv\Scripts\python.exe" ozon_session_probe.py --engine camoufox
) else (
    ".venv\Scripts\python.exe" ozon_session_probe.py %*
)

echo.
pause
