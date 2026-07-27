@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo    Установка парсера цен WB/Ozon (Windows)
echo ============================================

where python >nul 2>nul || (echo [ERROR] Python не найден. Установите Python 3.10+ и повторите. & pause & exit /b 1)

echo [1/4] venv...
if exist venv rmdir /s /q venv
python -m venv venv

echo [2/4] зависимости (десктоп)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt

echo [3/4] конфиг...
if not exist config.json copy config.example.json config.json >nul

echo [4/4] ярлык запуска...
> run_parser.bat echo @echo off
>> run_parser.bat echo chcp 65001 ^>nul
>> run_parser.bat echo cd /d "%~dp0"
>> run_parser.bat echo call venv\Scripts\activate.bat
>> run_parser.bat echo python cli.py
>> run_parser.bat echo pause

echo ============================================
echo [ГОТОВО] Запуск: run_parser.bat
echo ============================================
pause
