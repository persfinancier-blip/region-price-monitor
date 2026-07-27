#!/usr/bin/env bash
# Linux-сервер: установка ядра (без браузера) и запуск сбора цен.
# Прогрев кук делается на ДЕСКТОПЕ; сюда копируется папка profiles/.
set -e
cd "$(dirname "$0")"

if [ ! -d venv ]; then
  python3 -m venv venv
  ./venv/bin/pip install --upgrade pip
  ./venv/bin/pip install -r requirements.txt        # только ядро, без uc/selenium
fi

# PG берётся из окружения (.env). Подхватим, если есть.
[ -f .env ] && set -a && . ./.env && set +a

./venv/bin/python collect.py "$@"

# ── Расписание (пример crontab, каждый день в 07:00) ──
#   0 7 * * *  /opt/rpm/server_run.sh >> /var/log/rpm.log 2>&1
