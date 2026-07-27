@echo off
chcp 65001 >nul
cd /d "%~dp0parser\core"
echo ============================================
echo    WB/Ozon price parser - install
echo ============================================
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.10+ not found: https://www.python.org/downloads/
  pause
  exit /b 1
)
echo [1/3] Creating virtual environment...
if exist venv rmdir /s /q venv
python -m venv venv
echo [2/3] Installing dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo [3/3] Config...
if not exist config.json copy config.example.json config.json >nul
if not exist "%~dp0parser\results" mkdir "%~dp0parser\results"
echo ============================================
echo [DONE] Open: parser\run_parser.bat
echo ============================================
pause
