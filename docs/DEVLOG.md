# DEVLOG — region-price-monitor

Журнал пассов. Каждый пасс воркера заканчивается записью здесь (дата, промпт, что сделано, что проверено).

## 2026-07-22 — Спайк осуществимости (`prompt-00-spike`)

- Собрана вся стартовая документация: TZ, 4 ADR, ARCHITECTURE, ROADMAP, BACKLOG, промпты.
- Проведён ручной спайк через мобильный прокси (mobileproxy.space) скриптом `spike/check_price.py`.
- **Проверено на живых данных:** прокси даёт мобильный IP РФ (МегаФон, Мурманск); WB отдаёт цену SKU через `card.wb.ru/cards/v4/detail`; цена **отличается по региону** (МСК 2940 ₽ vs ВЛ 2975 ₽); Ozon блокирует голый запрос (403) → нужен Playwright.
- Ozon браузером на триал-прокси не поехал: Chromium виснет даже на лёгком сайте в ОБОИХ режимах авторизации (логин/пароль и IP-whitelist), хотя `requests` идёт — диагноз: несовместимость дешёвого мобильного триал-прокси с браузером, не логика Ozon. Риск не архитектурный.
- **Вердикт: GO для старта.** Ozon-проб переносится на нормальный прокси (перед Фазой 4). Урок: прокси выбирать с проверкой на работу с браузером. Детали — `docs/spike-report.md`.

## 2026-07-22 — Расширенный спайк Ozon + решения по методу и панели

- **Закрыт Ozon-проб.** На прокси ASocks (HTTPS-схема, мобильные IP РФ) доказан рабочий метод чтения Ozon **без браузера и без капчи**: прогретые куки (разово из браузера) + `curl_cffi` с TLS под Chrome. Обычный `requests` даёт 403 (TLS-фингерпринт) — ключевой факт. Живой замер: товар 3129447770 → HTTP 200, цена 2682 / без карты 5900 / с Ozon-картой 2414 ₽.
- **Регион подтверждён в куках:** смена города доставки меняет цену с одного IP (десятки регионов без парка прокси для чтения Ozon).
- **Метод сбора обновлён:** WB — `requests`; Ozon — `curl_cffi`+куки; браузер только для прогрева кук. Оформлено в [ADR-0005](adr/0005-scraping-method-update.md) (заменяет ADR-0002); ROADMAP и TZ синхронизированы.
- **Расширен объём (владелец):** продукт **Prizma** с панелью управления и zip-автоустановщиком (Win+Linux). Оформлено в [ADR-0006](adr/0006-panel-and-delivery.md) и [SPEC-panel.md](SPEC-panel.md); сделаны логотип (`assets/prizma-logo.svg`) и мокапы дашборда в стиле бренд-бука «Вектор·OS». Пункт «UI не делаем» из TZ снят.
- **Готовность:** к разработке ядра сбора — GO. Следующая веха — **Фаза 0 (скелет, `prompt-01-skeleton`)**.
- Спайк-скрипты: `spike/check_ozon.py` (прогрев кук), `spike/check_ozon_cookies.py` (быстрое чтение). Открытые follow-up: определить региональную куку, измерить TTL кук, прогрев на Linux.

## 2026-07-22 — Скелет и тулинг (`prompt-01-skeleton`)

- Пакет `app/` (async): `config.py` (pydantic-settings), `db.py` (async engine/session + `healthcheck()`), `cli.py` (`healthcheck` команда); пустые пакеты `collectors/`, `proxy/`, `queue/`, `scheduler/` под будущие фазы.
- `pyproject.toml`: рантайм-зависимости (sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, requests, curl_cffi, playwright, apscheduler, structlog) + dev-группа под `[project.optional-dependencies]`; ruff/mypy настроены.
- Alembic инициализирован (async-шаблон), `env.py` подключён к `app.db.Base.metadata` и берёт URL из `Settings`; `alembic upgrade head` **проверен вживую** на `docker compose up postgres` — проходит на пустой схеме.
- `Dockerfile` (база Playwright Python) + `docker-compose.yml` (app + postgres:16 + volume); `cli healthcheck` **проверен вживую** против compose-postgres — отвечает OK.
- `scripts/dod.sh`: устанавливает проект (`pip install -e ".[dev]"`) на голом раннере, затем ruff check + ruff format --check + mypy (strict) + pytest — **прогнан локально в чистом venv, зелёный**.
- `.env.example` добавлен; `.env` в `.gitignore`; секретов в диффе нет.
- Итог: Фаза 0 закрыта. Следующая веха — Фаза 1 (`prompt-02-schema`).
