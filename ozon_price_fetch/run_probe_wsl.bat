@echo off
REM ASCII-only by design: Windows CMD breaks on non-ASCII in .bat files.
REM Runs the probe inside WSL2 with Xvfb - the exact reference configuration.
chcp 65001 >nul
cd /d "%~dp0"

echo === Ozon probe via WSL2 (Xvfb, reference config) ===
echo.

where wsl >nul 2>&1
if errorlevel 1 (
    echo [ERROR] WSL not found.
    echo         Install it once from an ADMIN PowerShell:  wsl --install
    echo         Then reboot and run this file again.
    pause
    exit /b 1
)

wsl -e true >nul 2>&1
if errorlevel 1 (
    echo WSL is present, but no Linux distribution is installed yet.
    echo Ubuntu is about 500 MB and installs once.
    echo.
    choice /C YN /N /M "Install Ubuntu now? [Y/N] "
    if errorlevel 2 (
        echo.
        echo Cancelled. To do it manually, run in PowerShell:
        echo     wsl --install -d Ubuntu
        pause
        exit /b 1
    )
    echo.
    echo Installing Ubuntu, this takes a few minutes...
    wsl --install -d Ubuntu
    echo.
    echo -----------------------------------------------------------
    echo  A new window will ask for a UNIX username and password.
    echo  Pick anything short. REMEMBER THE PASSWORD - the setup
    echo  script needs it for sudo.
    echo.
    echo  When Ubuntu is ready, run this file again.
    echo -----------------------------------------------------------
    pause
    exit /b 0
)

echo Passing control to WSL...
echo.
wsl -e bash -lc "cd \"$(wslpath '%CD%')\" && bash run_probe_wsl.sh %*"

echo.
pause
