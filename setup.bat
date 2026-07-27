@echo off
rem ASCII-only messages to avoid console mojibake in cmd.exe
cd /d "%~dp0"
echo ============================================
echo    WB/Ozon price parser - Windows setup
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.10+ from https://www.python.org/downloads/ then re-run.
  pause
  exit /b 1
)

echo [1/4] Creating virtual environment...
if exist venv rmdir /s /q venv
python -m venv venv

echo [2/4] Installing desktop dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt

echo [3/4] Config...
if not exist config.json copy config.example.json config.json >nul

echo [4/4] Creating launcher run_parser.bat...
> run_parser.bat echo @echo off
>> run_parser.bat echo chcp 65001 ^>nul
>> run_parser.bat echo cd /d "%%~dp0"
>> run_parser.bat echo call venv\Scripts\activate.bat
>> run_parser.bat echo python cli.py
>> run_parser.bat echo pause

echo ============================================
echo [DONE] Start the app: run_parser.bat
echo ============================================
pause
