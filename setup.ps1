#requires -Version 5.1
# WB/Ozon Parser — установка на Windows (десктоп: прогрев + сбор)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Установка парсера цен WB/Ozon (Windows)"  -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Python
try { $pv = & python --version 2>&1; Write-Host "[OK] $pv" -ForegroundColor Green }
catch { Write-Host "[ERROR] Python не найден. Установите Python 3.10+: https://www.python.org/downloads/" -ForegroundColor Red; Read-Host "Enter"; exit 1 }

# Chrome
$chromeOk = $false
foreach ($p in @("HKCU:\Software\Google\Chrome\BLBeacon","HKLM:\Software\Google\Chrome\BLBeacon","HKLM:\Software\WOW6432Node\Google\Chrome\BLBeacon")) {
    try { $v=(Get-ItemProperty -Path $p -Name version -ErrorAction Stop).version; Write-Host "[OK] Chrome $v" -ForegroundColor Green; $chromeOk=$true; break } catch {}
}
if (-not $chromeOk) { Write-Host "[WARN] Google Chrome не найден — нужен для прогрева кук. Установите: https://www.google.com/chrome/" -ForegroundColor Yellow }

Write-Host "[1/4] venv..." -ForegroundColor Cyan
if (Test-Path "$root\venv") { Remove-Item "$root\venv" -Recurse -Force }
& python -m venv "$root\venv"
$py = "$root\venv\Scripts\python.exe"

Write-Host "[2/4] зависимости (десктоп)..." -ForegroundColor Cyan
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r "$root\requirements-desktop.txt"

Write-Host "[3/4] конфиг..." -ForegroundColor Cyan
if (-not (Test-Path "$root\config.json")) { Copy-Item "$root\config.example.json" "$root\config.json" }

Write-Host "[4/4] ярлык запуска..." -ForegroundColor Cyan
$bat = @"
@echo off
chcp 65001 >nul
cd /d "$root"
call "$root\venv\Scripts\activate.bat"
python cli.py
pause
"@
Set-Content -Path "$root\run_parser.bat" -Value $bat -Encoding UTF8

try {
    $desktop=[Environment]::GetFolderPath("Desktop")
    $sc=(New-Object -ComObject WScript.Shell).CreateShortcut("$desktop\Парсер WB-Ozon.lnk")
    $sc.TargetPath="$root\run_parser.bat"; $sc.WorkingDirectory=$root
    $sc.IconLocation="$env:SystemRoot\System32\SHELL32.dll,13"; $sc.Save()
} catch {}

Write-Host "============================================" -ForegroundColor Green
Write-Host "[ГОТОВО] Запуск: run_parser.bat (или ярлык на рабочем столе)" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Read-Host "Enter"
