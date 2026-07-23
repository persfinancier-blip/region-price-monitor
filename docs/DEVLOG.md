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

## 2026-07-22 — Модель данных и миграции (`prompt-02-schema`)

- `app/enums.py`: `Marketplace`, `RunMode`, `RunStatus`, `QueueStatus`, `Outcome` — `enum.StrEnum`, персистятся как нативные PG `ENUM`.
- `app/models.py`: все шесть таблиц (`products`, `regions`, `runs`, `measure_queue`, `price_snapshots`, `attempts`) на SQLAlchemy 2.0 (`Mapped`/`mapped_column`), `JSONB` под гео/статистику/сырые данные, `Numeric` под деньги; индексы `price_snapshots (product_id, region_id, captured_at desc)` и `measure_queue (status, run_id)`.
- Первая Alembic-миграция (autogenerate + ручная проверка): создаёт все enum'ы, таблицы, FK и оба индекса; downgrade явно дропает enum'ы (иначе повторный upgrade падал бы). **Проверено вживую** на `docker compose up postgres`: `upgrade head` → `downgrade base` → `upgrade head` — чисто, без ошибок.
- `app/repositories.py`: `ProductRepository`/`RegionRepository` — идемпотентный `upsert` через `ON CONFLICT DO UPDATE ... RETURNING`. Нашли и починили баг: без `execution_options={"populate_existing": True}` ORM возвращал закэшированный (устаревший) объект из identity map вместо обновлённой строки — второй `upsert` в той же сессии молча не отражал новые значения.
- CLI: `import-products` / `import-regions` грузят JSON и апсертят через репозитории; **проверено вживую** — повторный запуск с изменённым полем корректно обновляет строку, не создавая дублей.
- Демо-набор: `data/seed/products.json` (2×WB + 2×Ozon), `data/seed/regions.json` (msk/spb/nsk с гео под WB `dest` и Ozon город/координаты).
- `tests/test_repositories.py`: 4 теста на upsert-идемпотентность и `list_active` для обеих таблиц; фикстура поднимает `alembic upgrade head` и скипает модуль, если `TEST_DATABASE_URL`/`DATABASE_URL` не задан или БД недоступна. **Прогнано вживую** с `TEST_DATABASE_URL` — зелёные; без БД — чисто скипаются (DoD-гейт в CI не требует Postgres).
- Итог: Фаза 1 закрыта. Следующая веха — Фаза 2 (`prompt-03-wb-collector`).

## 2026-07-22 — Коллектор WB, домашний регион, без прокси (`prompt-03-wb-collector`)

- `app/collectors/base.py`: DTO `PriceObservation` (frozen dataclass, деньги — `Decimal`) и контракт `MarketplaceCollector` (`Protocol`).
- `app/collectors/wb_parse.py`: чистая функция `parse_wb_card` — разбирает ответ `card.wb.ru` v2 (копейки → `Decimal`, `price_base`/`price` из `basic`/`product`, `price_card = None` в этой фазе — WB-кошелёк считается на клиенте и не приходит в этом эндпоинте), `is_available` по `stocks[].qty > 0`, `ValueError` на пустой/заблокированный ответ.
- `app/collectors/wb.py`: `WbCollector` (`requests`, без прокси) — собирает запрос из `region.geo["wb"]["dest"]` и `product.sku`, заголовки из спайка (без brotli), таймаут и URL из конфига.
- `app/config.py`: добавлены `home_region`, `wb_card_url`, `http_timeout_s`.
- `app/repositories.py`: `RunRepository` (`create`/`finish`), `PriceSnapshotRepository` (`add`, insert-only); точечные `get_by_code`/`get_by_sku` для CLI-обвязки.
- CLI: `measure-wb` (`--region`, `--sku`) — создаёт `run`, гоняет коллектор через `asyncio.to_thread`, пишет снапшоты, считает ok/failed, печатает сводку; отказ по одному товару не роняет весь run.
- `tests/fixtures/wb_card_sample.json` + `tests/test_wb_parse.py`: 6 юнит-тестов на `parse_wb_card` без сети — цены из копеек, `price_card is None`, `currency == RUB`, доступность true/false, `ValueError` на пустой `products`.
- `pyproject.toml`: `types-requests` в dev-экстре (`requests` уже был в рантайм-зависимостях с Фазы 0).
- DoD-гейт (`scripts/dod.sh`) зелёный: ruff + mypy(strict) + pytest — 7 passed, 1 skipped (DB-тест чисто скипается без Postgres).
- Живая проверка `measure-wb` против реального WB и локального Postgres **не выполнена** в этом пассе — в песочнице нет сетевого доступа к `card.wb.ru` и поднятого Postgres; логика и парсинг проверены юнит-тестами на закоммиченном сэмпле. Требуется ручная проверка владельцем перед закрытием фазы.
- Итог: код Фазы 2 готов, DoD зелёный. Следующая веха — Фаза 3 (`prompt-04-regions-proxy`).

## 2026-07-23 — Регионализация + ProxyProvider (`prompt-04-regions-proxy`)

- `app/proxy/base.py`: `RegionCode`, frozen `ProxyLease` (`provider`, `region_code`, `proxy_url`, `ref` — некредный маскированный лейбл), `ProxyProvider` (`Protocol`: `acquire`/`report`) по ADR-0003; хелпер `proxy_url_to_requests_dict`.
- `app/proxy/static.py`: `StaticProxyProvider` — резолвит регион в прокси из `{region_code: proxy_url}` (конфиг), unknown-регион → глобальный `proxy_url` либо прямое соединение (`None`); `ref` маскируется до хоста (без кредов). `report` — no-op (debug-лог), здоровье/ротация — Фаза 6. `make_proxy_provider(settings)` — фабрика по `settings.proxy_provider` (`"static"`; неизвестное значение — явная ошибка). Вендор нигде не хардкожен.
- `app/config.py` / `.env.example`: добавлен `proxy_map_json` (JSON `{region_code: proxy_url}`, парсится провайдером; невалидный JSON — явная ошибка при конструировании).
- `app/collectors/base.py` / `wb.py`: `collect(..., proxy_url=None)` — прокидывает `proxies=` в `requests.get`; `proxy_url=None` = поведение Фазы 2 (прямое соединение) без изменений. Новый `WbCollectionError` несёт `status_code`/`empty_products` для классификации исхода.
- `app/collectors/outcome.py`: чистая `classify_outcome` — 200+товары → `OK`; 403/429 → `HARD_BAN`; `requests.Timeout` → `TIMEOUT`; прочие исключения → `ERROR`; 200 с пустыми `products` → `SOFT_BAN` (триггер: валидный ответ, но `parse_wb_card` не нашёл товаров).
- `app/repositories.py`: `MeasureQueueRepository` (`create`/`mark`), `AttemptRepository` (`add`) — обе insert/update без блокировок (`SKIP LOCKED` — Фаза 5).
- CLI `measure-wb`: `--region` теперь повторяемый/опциональный (по умолчанию — все активные регионы); по паре (товар, регион) — создаёт `measure_queue`, берёт `ProxyLease`, замеряет длительность, классифицирует исход, пишет `price_snapshot` при `OK`, всегда пишет `attempts` (`proxy_ref` — маскированный, без кредов), помечает queue-item `done`/`failed`, вызывает `provider.report(...)`; отказ по одной паре не роняет run; `run.stats` — агрегат по исходам; печатается сводка по каждой паре.
- Тесты: `tests/test_proxy_static.py` (маппинг региона, фолбэк, direct, невалидный JSON), `tests/test_outcome.py` (все ветки классификатора), `tests/test_measure_wb.py` (DB-тест: `measure-wb` пишет `measure_queue` + `attempts` + снапшот на `OK`; скипается чисто без БД, по паттерну Фазы 1). `test_wb_parse.py` не тронут, зелёный.
- Живых прокси/реального WB в песочнице нет — сетевой сценарий (регион-разные цены) требует ручной проверки владельцем с реальным `proxy_map_json`.
- Итог: код Фазы 3 готов, DoD зелёный (ruff + mypy strict + pytest: DB-тесты скипаются чисто без Postgres). Следующая веха — Фаза 4 (`prompt-05-ozon-collector`).

## 2026-07-23 — Коллектор Ozon (`prompt-05-ozon-collector`)

- `app/cookies/base.py`: `CookieBundle` (frozen dataclass — маркетплейс, регион, полный `storage_state`, `warmed_at`, `stale`, немаскированный `source_ref`), `CookieStore` (`Protocol`: `load`/`save`/`mark_stale`), чистая `is_stale` (TTL-истечение **или** явный флаг).
- `app/cookies/fs.py`: `FsCookieStore` — один JSON-файл на `cookie_store_dir/{marketplace}/{region_code}.json`; куки никогда не логируются; `make_cookie_store(settings)` — фабрика (пока только `fs`, БД-хранилище — Фаза 8).
- `app/cookies/warm.py`: `CookieWarmer` продюсирует `spike/check_ozon.py` — реальный Chromium через Playwright, city-хинт из `region.geo["ozon"]`, `MANUAL=1` ждёт оператора (капча/город), сохраняет `storage_state`; при наличии `proxy_url` браузер идёт через тот же прокси (гибридная модель, warm-IP == fetch-IP). `warm_if_stale` — перегревает только при отсутствии/протухании.
- `app/collectors/ozon_parse.py`: чистая `parse_ozon` — разбирает `widgetStates` composer-api (`webPrice*`, значения — JSON-в-JSON), `price`/`originalPrice`/`cardPrice`, `currency="RUB"`, доступность по отсутствию `webOutOfStock`; `OzonParseError` на пустой/антибот-ответ.
- `app/collectors/ozon.py`: `OzonCollector` — грузит `CookieBundle` по `(OZON, region.code)`, `OzonCookiesUnavailable` **до** сетевого вызова при отсутствии/протухании; запрос через `curl_cffi.requests.get(..., impersonate="chrome")` (обычный `requests` — 403, JA3-отпечаток); `proxy_url=None` — куки несут регион напрямую, `proxy_url` задан — гибридная маршрутизация через `StaticProxyProvider`; `OzonCollectionError(status_code, anti_bot)` зеркалит `WbCollectionError`.
- `app/collectors/outcome.py`: `classify_outcome` расширен параметром `anti_bot` (без новых значений `Outcome`) и распознаёт `curl_cffi.requests.exceptions.Timeout` как `TIMEOUT`; 403/429/`anti_bot` → `HARD_BAN`.
- `app/config.py` / `.env.example`: `ozon_api_url`, `ozon_impersonate`, `cookie_store_dir`, `ozon_cookie_ttl_hours` (12ч по умолчанию, time-based). `.gitignore`: `data/cookies/` — куки никогда не попадают в репозиторий.
- CLI: `measure-ozon` (зеркалит `measure-wb`) — в интерактивном режиме прогревает куки по требованию (`warm_if_stale`), в неинтерактивном — протухшую/отсутствующую пару пропускает без фиктивной попытки («needs warm»); при `HARD_BAN` помечает куки протухшими (`mark_stale`) — следующий прогрев переустановит их. `warm-ozon` — прогревает куки для всех активных Ozon-регионов (или `--region`).
- Тесты (без сети, без браузера): `tests/test_ozon_parse.py` (парсер на закоммиченном composer-api сэмпле — цена/база/карта/доступность, ошибка на пустом/антибот-ответе), `tests/test_cookie_store.py` (`FsCookieStore` round-trip, `is_stale` по TTL и по флагу, `mark_stale`), `tests/test_outcome.py` расширен (Ozon 200→OK, 403→HARD_BAN, anti_bot→HARD_BAN, curl_cffi timeout→TIMEOUT, transport→ERROR). Все зелёные; более ранние фазы не тронуты.
- Открытые вопросы обновлены: региональная кука Ozon → решение принято (хранить полный набор на город, ADR-0005); TTL кук → заведён как конфиг `ozon_cookie_ttl_hours`, предстоит измерить на живом прототипе.
- Живой сценарий (два города, разные `cardPrice` только по кукам; проверка `proxy_map_json` для одного города) не выполнен в песочнице — нет браузера/сети для реального прогрева; требуется ручная проверка владельцем.
- Итог: код Фазы 4 готов, DoD зелёный (ruff + mypy strict + pytest: DB-тесты скипаются чисто без Postgres). Следующая веха — Фаза 5 (`prompt-06-orchestration`).

## 2026-07-23 — Оркестрация: Scheduler + очередь-в-Postgres + worker pool (`prompt-06-orchestration`)

- `app/queue/base.py`: `Pair`/`QueueItem` (frozen DTO) и `TaskQueue` (`Protocol`: `enqueue`/`claim`/`complete`/`reclaim_stale`) — эскиз из ARCHITECTURE.md.
- `app/queue/postgres.py`: `PgTaskQueue` поверх `measure_queue` — `claim` строго через `SELECT ... FOR UPDATE SKIP LOCKED` (select+update статуса в одной транзакции), `reclaim_stale` возвращает протухшие `in_progress` (`locked_at` старше TTL) обратно в `pending`. `make_task_queue(session)` — фабрика (пока только Postgres).
- `app/collectors/measure.py`: `measure_pair(...)` — вынесенное из `_measure_wb`/`_measure_ozon` тело замера одной пары (аренда прокси → таймер → `collect` в потоке → классификация → снапшот на `OK` → `attempts` всегда → Ozon `mark_stale` на `HARD_BAN` → `provider.report`); диспатч WB/Ozon по `product.marketplace`; для Ozon сохранён контракт «нужен прогрев — пропуск без фиктивной попытки» (сентинел `None`). Статус queue-item выставляет вызывающий код, не сам `measure_pair`.
- `app/scheduler/retry.py`: чистые `backoff_delay` (экспоненциальный, capped) и `is_retriable` (`HARD_BAN`/`TIMEOUT`) — без сна, юнит-тестируемые напрямую.
- `app/scheduler/runner.py`: `run_once(...)` — создаёт `run`, ставит в очередь все активные пары (WB — все активные регионы, Ozon — с `ozon` гео), гоняет worker pool (`asyncio.Semaphore` на `max_concurrency`, каждый воркер: `claim` батч → `measure_pair` с ретраем по `retry_limit`/backoff → `complete`) до опустошения очереди, агрегирует `runs.stats`; `Scheduler` — обёртка над `AsyncIOScheduler` (APScheduler), cron-джоба на `settings.schedule_cron` вызывает `run_once(mode=SCHEDULED)`.
- CLI: `measure-wb`/`measure-ozon` переведены на общий `measure_pair` (поведение не изменилось, интерактивный прогрев Ozon остался в CLI перед вызовом); добавлены `run-once` (один полный прогон по всем активным парам, `RunMode.MANUAL`, неинтерактивный) и `serve` (APScheduler-демон, блокирует до Ctrl-C).
- `app/config.py` / `.env.example`: `queue_claim_batch`, `retry_backoff_base_s`, `retry_backoff_max_s`, `queue_lock_ttl_s`.
- Тесты: `tests/test_retry.py` (чистые, backoff монотонен и capped, `is_retriable` по всем исходам), `tests/test_queue.py` (DB: `enqueue`+`claim` заполняет и блокирует статус, **два конкурентных `claim()` в разных сессиях возвращают непересекающиеся наборы** — доказывает `SKIP LOCKED`, `complete` выставляет терминальный статус, `reclaim_stale` возвращает протухший `in_progress` в `pending`), `tests/test_runner.py` (DB: `run_once` со стаб-коллектором — `price_snapshot` на `OK`, ретраи ограничены `retry_limit`, по `attempts`-строке на попытку). Все DB-тесты чисто скипаются без `TEST_DATABASE_URL`/`DATABASE_URL` и проходят с локальным Postgres (проверено вживую: 61 passed на чистой БД).
- Ручная проверка вживую: `run-once` с демо-товаром/регионом на локальном Postgres прошла полный цикл (run created → enqueue → worker pool → attempt/queue-item записаны → `run.status=done`); реальной сети/прокси в песочнице нет, поэтому запрос к WB вернул `error` (ожидаемо для фиктивного SKU/dest) — логика оркестрации подтверждена, не сетевой сценарий.
- Итог: код Фазы 5 готов, DoD зелёный (ruff + mypy strict + pytest). Следующая веха — Фаза 6 (`prompt-07-resilience`).

## 2026-07-23 — Наблюдаемость: метрики + структурные логи + алерт по доле успеха (`prompt-07-observability`)

- `app/obs/logging.py`: stdlib-only `JsonFormatter` (level/logger/message/timestamp + `extra`-поля, без
  `structlog`), `configure_logging(settings)` ставит форматтер на root-логгер (`json` | `text` по
  `settings.log_format`); вызывается один раз в начале `app/cli.py::main`.
- `app/collectors/measure.py::measure_pair`: одно структурное `measurement`-событие на попытку
  (`run_id`, `marketplace`, `product_id`, `sku`, `region_code`, `proxy_ref` — маскированный,
  `outcome`, `duration_ms`, `error`) — единственная точка per-attempt телеметрии; CLI и воркер-пул
  получают её бесплатно, оба идут через `measure_pair`. Поведение/возврат `measure_pair` не изменены.
- `app/obs/metrics.py`: `RunMetrics` (frozen dataclass), чистая `metrics_from_counts` (юнит-тестируема
  без БД, guard на деление на ноль, `attempts_per_success = total/ok`, `ok==0 → total` как
  худший случай), `compute_run_metrics(session, run_id)` — агрегирует `attempts` через join на
  `measure_queue` (`func.count` по `outcome`, `func.coalesce(func.sum(duration_ms), 0)`),
  `to_prometheus(metrics)` — Prometheus text-exposition строкой, без `prometheus_client`.
- `app/obs/alerts.py`: `Alert` (frozen dataclass), `Alerter` (`Protocol`, зеркалит `ProxyProvider` из
  ADR-0003), `LogAlerter` (структурный WARN, без конфига), `WebhookAlerter` (`requests.post` в
  `asyncio.to_thread`, JSON-тело, сбой логируется и не роняет ран), чистая `should_alert(metrics,
  threshold, min_measures)`, `make_alerter(settings)` — фабрика (`log` дефолт; `webhook` требует
  `alert_webhook_url`, иначе явная ошибка).
- `app/scheduler/runner.py::run_once`: `run.started` в начале, после `run_repo.finish` —
  `compute_run_metrics(run_id)` в отдельной read-сессии, `run.finished` со всеми метриками,
  `make_alerter(settings)` + `should_alert(...)` → `alerter.send(Alert(...))`; алертинг обёрнут в
  `try/except` — сбой никогда не роняет и не откатывает ран. `RunSummary` расширен полем `metrics`.
- `app/config.py` / `.env.example`: `log_level`, `log_format`, `success_rate_threshold` (0.9 по TZ),
  `alert_min_measures`, `alerter`, `alert_webhook_url`.
- CLI: `configure_logging(get_settings())` в начале `main`; новая команда `metrics --run <id> |
  --last` — печатает человекочитаемую сводку, Prometheus text и одну структурную лог-строку.
- Тесты: `tests/test_metrics.py` (чистая арифметика — все ветки, divide-by-zero guard, Prometheus
  well-formed; DB-тест агрегации на смешанных `attempts`), `tests/test_alerts.py` (`should_alert` по
  порогу/`min_measures`, `LogAlerter` через `caplog`, `WebhookAlerter` — payload/URL с
  monkeypatched `requests.post`, без реальной сети, сбой не бросает исключение),
  `tests/test_logging.py` (валидный JSON, ожидаемые ключи, отсутствие `Decimal`/цены и сырого
  proxy URL в представительном `extra`), искусственный бан в `tests/test_runner.py`
  (ретраи по `retry_limit` → `ban_rate > 0`/`attempts_per_success > 1`; алерт срабатывает ровно
  один раз ниже порога и ноль раз на пороге/выше — через spy-`Alerter`). Все DB-тесты чисто
  скипаются без `TEST_DATABASE_URL`/`DATABASE_URL`; вживую на локальном Postgres 16 — 83 passed.
- Живая проверка: `run-once` на локальном Postgres — структурные JSON-логи (`measurement` на
  попытку, `run.started`/`run.finished` с метриками, `alert` WARN при доле успеха 0 < 0.9);
  `metrics --last` печатает сводку и корректный Prometheus text по тем же данным.
- `docs/adr/0007-observability.md` фиксирует 4 решения (метрики из БД, нет live-эндпоинта,
  `Alerter`-сиим, здоровье прокси/антибот — в `prompt-08`).
- Итог: код первой половины Фазы 6 готов, DoD зелёный (ruff + mypy strict + pytest). Следующая
  веха — вторая половина Фазы 6, `prompt-08` (здоровье прокси/cooldown + антибот-тюнинг).

## 2026-07-23 — Фаза 6, часть 2: здоровье прокси/cooldown + антибот-тюнинг (`prompt-08-proxy-health`)

- **Здоровье прокси — из `attempts`, без новой схемы** (`app/proxy/health.py`, ADR-0007 §4):
  чистая `evaluate_health(ban_count, last_ban_at, now, threshold, cooldown_s) -> HealthVerdict`;
  `ProxyHealthService` агрегирует недавние `HARD_BAN`/`SOFT_BAN` для `proxy_ref` в скользящем
  окне (`proxy_health_window_s`) коротким read-запросом; `HealthAwareProxyProvider` — декоратор
  над базовым `ProxyProvider` (сиим ADR-0003 не тронут): `acquire` бросает `ProxyOnCooldown`,
  если прокси остывает, `report` делегирует + логирует `proxy.health`. На ошибке health-сервиса —
  fail-open (не остывающий) с логом, ран не падает.
- **`make_proxy_provider(settings, session_factory=...)`** оборачивает `StaticProxyProvider` в
  `HealthAwareProxyProvider`, когда `proxy_health_enabled` и передан `session_factory`; без
  фактора (CLI `measure-*`) поведение не меняется. `runner.py` передаёт `session_factory` в
  воркеры.
- **Cooldown → чистый скип** (`measure_pair`): `ProxyOnCooldown` ловится до сетевого вызова,
  логируется `proxy.cooldown` (region, proxy_ref, until), возвращается тот же sentinel `None`,
  что и Ozon-прогрев — без фейкового `attempts`-ряда; в `_process_item` это уже терминально
  (без ретрая).
- **Антибот-темп** (`app/collectors/pacing.py`): `RateLimiter` — мин. интервал + случайный
  джиттер на маркетплейс (`wb_min_interval_s`, `ozon_min_interval_s`, `request_jitter_s`), один
  инстанс на пул воркеров (не на воркера); `NullRateLimiter` — дефолт для `measure_pair`, чтобы
  CLI и тесты не зависели от паттерна.
- **Fingerprint-консистентность** (`app/collectors/fingerprint.py`): `wb_headers(region)` —
  детерминированный по региону UA/`sec-ch-ua` (стабильный хэш кода региона → индекс в списке
  разрешённых identity, дефолт сохранён на индексе 0); `ozon_impersonate(region, settings)` —
  аналогично для `curl_cffi`. Никогда не рандомизируется по запросу — только по региону.
- **Конфиг**: `proxy_health_enabled/proxy_ban_threshold/proxy_health_window_s/proxy_cooldown_s`,
  `wb_min_interval_s/ozon_min_interval_s/request_jitter_s` — в `app/config.py` и `.env.example`.
- Тесты: `tests/test_proxy_health.py` (чистая арифметика `evaluate_health` — все ветки и
  граница `until`; декоратор с зафейканным сервисом — cooldown/passthrough/fail-open; DB-тест
  `ProxyHealthService.verdict` на живых `attempts`), `tests/test_pacing.py` (мин.интервал +
  джиттер с патченным `asyncio.get_running_loop`/`sleep` — без реального сна),
  `tests/test_fingerprint.py` (детерминизм по региону, дефолт в разрешённом множестве),
  `tests/test_runner.py::test_run_once_skips_cooling_down_region_without_attempt` (стаб-провайдер
  с `ProxyOnCooldown` → скип без attempt-ряда, терминальный queue item, `ban_rate` не растёт).
  Вживую на локальном Postgres 16 — 105 passed (все более ранние фазы зелёные).
- ROADMAP/prompts-README/BACKLOG приведены в соответствие с разбивкой Фазы 6 на 6.1/6.2.
- Итог: Фаза 6 закрыта целиком. TZ-требование «устойчивость к антиботу» (остывание банов,
  человекоподобный темп, консистентный fingerprint) удовлетворено для MVP.
