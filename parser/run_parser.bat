@echo off
chcp 65001 >nul
cd /d "%~dp0core"
call venv\Scripts\activate.bat
python cli.py
pause
