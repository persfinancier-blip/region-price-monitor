@echo off
rem ── Запуск установки в обход политики PowerShell (двойной клик по этому файлу) ──
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if not errorlevel 1 goto :eof
echo.
echo [i] PowerShell nedostupen, zapuskayu setup.bat ...
call "%~dp0setup.bat"
