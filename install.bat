@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0parser\core"
echo ============================================
echo    WB/Ozon price parser - install
echo ============================================

set "PY_CMD=python"
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 goto :python_missing
  set "PY_CMD=py -3"
)

echo [1/3] Creating virtual environment...
if exist venv rmdir /s /q venv
%PY_CMD% -m venv venv
if errorlevel 1 goto :install_failed

call venv\Scripts\activate.bat
if errorlevel 1 goto :install_failed

echo [2/3] Installing dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :install_failed
python -m pip install -r requirements.txt
if errorlevel 1 goto :install_failed

echo [3/3] Config...
if not exist config.json copy config.example.json config.json >nul
if not exist "%~dp0parser\results" mkdir "%~dp0parser\results"

echo ============================================
echo [DONE] Open: parser\run_parser.bat
echo ============================================
if not defined RPM_INSTALL_NONINTERACTIVE pause
exit /b 0

:python_missing
echo [ERROR] Python 3.10+ not found: https://www.python.org/downloads/
if not defined RPM_INSTALL_NONINTERACTIVE pause
exit /b 1

:install_failed
echo [ERROR] Installation failed. Existing local config/profiles/results were not deleted.
if not defined RPM_INSTALL_NONINTERACTIVE pause
exit /b 1
