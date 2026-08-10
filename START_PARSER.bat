@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Region Price Monitor - sync and start

rem ===== Easy-to-change delivery settings =====
set "REPO_URL=https://github.com/persfinancier-blip/region-price-monitor.git"
if defined RPM_IMPLEMENTATION_BRANCH (
  set "BRANCH=%RPM_IMPLEMENTATION_BRANCH%"
) else (
  set "BRANCH=work/g01-implementation"
)

if defined RPM_LOCAL_ROOT (
  set "APP_ROOT=%RPM_LOCAL_ROOT%"
) else (
  set "APP_ROOT=%LOCALAPPDATA%\RegionPriceMonitor"
)
set "REPO_DIR=%APP_ROOT%\repo"

where git >nul 2>nul
if errorlevel 1 goto :git_missing

set "PY_CMD=python"
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 goto :python_missing
  set "PY_CMD=py -3"
)

if not exist "%APP_ROOT%" mkdir "%APP_ROOT%" >nul 2>nul

if not exist "%REPO_DIR%\.git" (
  if exist "%REPO_DIR%" goto :wrong_directory
  echo [INFO] Локальной копии нет. Скачиваю %BRANCH% ...
  git clone --branch "%BRANCH%" --single-branch "%REPO_URL%" "%REPO_DIR%"
  if errorlevel 1 goto :clone_failed
)

if not exist "%REPO_DIR%\tools\local_delivery.py" goto :helper_missing

echo [INFO] Проверяю и обновляю локальную копию...
%PY_CMD% "%REPO_DIR%\tools\local_delivery.py" --repo "%REPO_DIR%" --remote "%REPO_URL%" --branch "%BRANCH%" --launch
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :runtime_failed

exit /b 0

:git_missing
echo.
echo [ERROR] GIT_NOT_FOUND
 echo Git не найден. Установите Git for Windows и снова дважды кликните START_PARSER.bat.
goto :fail

:python_missing
echo.
echo [ERROR] PYTHON_NOT_FOUND
 echo Python 3 не найден. Установите Python 3.10+ и снова запустите START_PARSER.bat.
goto :fail

:wrong_directory
echo.
echo [ERROR] LOCAL_CHECKOUT_WRONG_DIRECTORY
 echo Папка "%REPO_DIR%" уже существует, но это не Git checkout.
 echo Скрипт ничего не удалял. Переименуйте папку вручную или пришлите этот экран разработчику.
goto :fail

:clone_failed
echo.
echo [ERROR] GIT_CLONE_FAILED
 echo Не удалось скачать репозиторий.
 echo Проверьте интернет. Если репозиторий станет приватным, войдите через Git Credential Manager.
goto :fail

:helper_missing
echo.
echo [ERROR] LOCAL_DELIVERY_HELPER_MISSING
 echo В checkout отсутствует tools\local_delivery.py. Обновление/запуск остановлены.
goto :fail

:runtime_failed
echo.
echo [ERROR] Локальная синхронизация или запуск завершились с кодом %RC%.
echo Если видите LOCAL_CHECKOUT_DIRTY, ничего не удаляйте: пришлите сообщение разработчику.
goto :fail

:fail
echo.
pause
exit /b 1
