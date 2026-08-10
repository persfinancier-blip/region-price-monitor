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

rem Use a dedicated G01 checkout next to this BAT file.
rem Existing legacy repositories such as C:\DEV\region-price-monitor are never touched.
if defined RPM_LOCAL_ROOT (
  set "REPO_DIR=%RPM_LOCAL_ROOT%\region-price-monitor-g01"
) else (
  set "REPO_DIR=%~dp0region-price-monitor-g01"
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
  echo [INFO] First run. Creating isolated G01 checkout...
  echo [INFO] Target: %REPO_DIR%
  echo [INFO] Branch: %BRANCH%
  git clone --branch "%BRANCH%" --single-branch "%REPO_URL%" "%REPO_DIR%"
  if errorlevel 1 goto :clone_failed
)

if not exist "%REPO_DIR%\tools\local_delivery.py" goto :helper_missing

set "PYTHONUTF8=1"
echo [INFO] Checking isolated G01 checkout and downloading updates...
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
echo Dedicated G01 folder already exists but is not a Git checkout:
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
echo The isolated checkout does not contain tools\local_delivery.py.
goto :fail

:runtime_failed
echo.
echo [ERROR] LOCAL_SYNC_OR_LAUNCH_FAILED code=%RC%
echo Do not delete local files. Send the complete error text to the developer.
goto :fail

:fail
echo.
pause
exit /b 1
