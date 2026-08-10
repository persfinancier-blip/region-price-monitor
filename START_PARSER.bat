@echo off
setlocal EnableExtensions
title Region Price Monitor - sync and start

rem Repository settings
set "REPO_URL=https://github.com/persfinancier-blip/region-price-monitor.git"
if defined RPM_IMPLEMENTATION_BRANCH (
  set "BRANCH=%RPM_IMPLEMENTATION_BRANCH%"
) else (
  set "BRANCH=work/g01-implementation"
)

rem By default keep the checkout next to this BAT file.
rem Example: C:\DEV\START_PARSER.bat -> C:\DEV\region-price-monitor
if defined RPM_LOCAL_ROOT (
  set "REPO_DIR=%RPM_LOCAL_ROOT%\region-price-monitor"
) else (
  set "REPO_DIR=%~dp0region-price-monitor"
)

where git >nul 2>nul
if errorlevel 1 goto :git_missing

set "PY_CMD=python"
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 goto :python_missing
  set "PY_CMD=py -3"
)

if not exist "%REPO_DIR%\.git" (
  if exist "%REPO_DIR%" goto :wrong_directory
  echo [INFO] First run. Cloning branch %BRANCH% ...
  git clone --branch "%BRANCH%" --single-branch "%REPO_URL%" "%REPO_DIR%"
  if errorlevel 1 goto :clone_failed
)

if not exist "%REPO_DIR%\tools\local_delivery.py" goto :helper_missing

set "PYTHONUTF8=1"
echo [INFO] Checking local checkout and downloading updates...
%PY_CMD% "%REPO_DIR%\tools\local_delivery.py" --repo "%REPO_DIR%" --remote "%REPO_URL%" --branch "%BRANCH%" --launch
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :runtime_failed

exit /b 0

:git_missing
echo.
echo [ERROR] GIT_NOT_FOUND
echo Install Git for Windows, then run START_PARSER.bat again.
goto :fail

:python_missing
echo.
echo [ERROR] PYTHON_NOT_FOUND
echo Install Python 3.10 or newer, then run START_PARSER.bat again.
goto :fail

:wrong_directory
echo.
echo [ERROR] LOCAL_CHECKOUT_WRONG_DIRECTORY
echo Folder already exists but is not the expected Git checkout:
echo %REPO_DIR%
echo Nothing was deleted.
goto :fail

:clone_failed
echo.
echo [ERROR] GIT_CLONE_FAILED
echo Check internet access and Git authentication.
goto :fail

:helper_missing
echo.
echo [ERROR] LOCAL_DELIVERY_HELPER_MISSING
echo File tools\local_delivery.py is missing in the checkout.
goto :fail

:runtime_failed
echo.
echo [ERROR] LOCAL_SYNC_OR_LAUNCH_FAILED code=%RC%
echo If you see LOCAL_CHECKOUT_DIRTY, do not delete anything. Send the error text to the developer.
goto :fail

:fail
echo.
pause
exit /b 1
