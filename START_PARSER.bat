@echo off
setlocal EnableExtensions
title Region Price Monitor - sync and start

rem Repository settings
set "REPO_URL=https://github.com/persfinancier-blip/region-price-monitor.git"
set "REPO_URL_ALT=https://github.com/persfinancier-blip/region-price-monitor"
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

rem Older checkouts may not contain the Python sync helper yet.
rem Bootstrap them with the same non-destructive policy.
if not exist "%REPO_DIR%\tools\local_delivery.py" goto :bootstrap_helper
goto :run_helper

:bootstrap_helper
echo [INFO] Local checkout is older than the sync helper. Bootstrapping safely...
set "ACTUAL_REMOTE="
for /f "usebackq delims=" %%R in (`git -C "%REPO_DIR%" remote get-url origin 2^>nul`) do set "ACTUAL_REMOTE=%%R"
if not defined ACTUAL_REMOTE goto :wrong_remote
if /I "%ACTUAL_REMOTE%"=="%REPO_URL%" goto :bootstrap_clean
if /I "%ACTUAL_REMOTE%"=="%REPO_URL_ALT%" goto :bootstrap_clean
goto :wrong_remote

:bootstrap_clean
set "DIRTY_TRACKED="
for /f "usebackq delims=" %%S in (`git -C "%REPO_DIR%" status --porcelain=v1 --untracked-files=no 2^>nul`) do set "DIRTY_TRACKED=1"
if defined DIRTY_TRACKED goto :dirty_checkout

echo [INFO] Fetching implementation branch...
git -C "%REPO_DIR%" fetch --prune origin "+refs/heads/%BRANCH%:refs/remotes/origin/%BRANCH%"
if errorlevel 1 goto :fetch_failed

set "ACTUAL_BRANCH="
for /f "usebackq delims=" %%B in (`git -C "%REPO_DIR%" symbolic-ref --quiet --short HEAD 2^>nul`) do set "ACTUAL_BRANCH=%%B"
if /I "%ACTUAL_BRANCH%"=="%BRANCH%" goto :bootstrap_ff

echo [INFO] Switching clean checkout from %ACTUAL_BRANCH% to %BRANCH% ...
git -C "%REPO_DIR%" show-ref --verify --quiet "refs/heads/%BRANCH%"
if errorlevel 1 goto :create_target_branch
git -C "%REPO_DIR%" switch "%BRANCH%"
if errorlevel 1 goto :branch_switch_failed
goto :bootstrap_ff

:create_target_branch
git -C "%REPO_DIR%" switch --track -c "%BRANCH%" "origin/%BRANCH%"
if errorlevel 1 goto :branch_switch_failed

:bootstrap_ff
git -C "%REPO_DIR%" merge-base --is-ancestor HEAD "origin/%BRANCH%" >nul 2>nul
if errorlevel 1 goto :diverged_checkout

git -C "%REPO_DIR%" merge --ff-only "origin/%BRANCH%"
if errorlevel 1 goto :fast_forward_failed

if not exist "%REPO_DIR%\tools\local_delivery.py" goto :helper_missing_after_update

:run_helper
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

:wrong_remote
echo.
echo [ERROR] LOCAL_CHECKOUT_WRONG_REMOTE
echo Existing checkout points to an unexpected Git origin.
echo Nothing was changed.
goto :fail

:dirty_checkout
echo.
echo [ERROR] LOCAL_CHECKOUT_DIRTY
echo Existing checkout has tracked local edits. Nothing was overwritten.
goto :fail

:branch_switch_failed
echo.
echo [ERROR] LOCAL_CHECKOUT_BRANCH_SWITCH_FAILED
echo Could not safely switch to %BRANCH%.
echo No reset, clean, or file deletion was attempted.
goto :fail

:diverged_checkout
echo.
echo [ERROR] LOCAL_CHECKOUT_DIVERGED
echo Implementation branch has local commits or diverged history. No reset was attempted.
goto :fail

:clone_failed
echo.
echo [ERROR] GIT_CLONE_FAILED
echo Check internet access and Git authentication.
goto :fail

:fetch_failed
echo.
echo [ERROR] GIT_FETCH_FAILED
echo Check internet access and Git authentication. Local files were not changed.
goto :fail

:fast_forward_failed
echo.
echo [ERROR] LOCAL_FAST_FORWARD_FAILED
echo Safe fast-forward failed. No reset or clean was attempted.
goto :fail

:helper_missing_after_update
echo.
echo [ERROR] LOCAL_DELIVERY_HELPER_MISSING
echo Safe update completed but tools\local_delivery.py is still missing.
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
