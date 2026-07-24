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

## 2026-07-23 — Фаза 7, часть 1 — Deploy core (`prompt-ops-01-deploy`)

- **Playwright-база переведена на `v1.47.0-noble`** (было `v1.44.0-jammy`): `jammy`-теги
  Playwright-образа несут Python 3.10, а `pyproject.toml` требует `>=3.12` — прод-сборка
  падала на `pip install .` («requires a different Python»), баг не был замечен раньше,
  т.к. `docker compose build` вживую не гонялся. `noble`-теги несут Python 3.12.3; `1.47.0`
  — самый ранний доступный `-noble` тег, совместим с `playwright>=1.44` из `pyproject.toml`.
- **Прод-`Dockerfile`**: сохранена Playwright-база (нужна для прогрева кук Ozon, ADR-0005);
  `pip install --no-cache-dir .` (без `-e`, без dev-экстры); `docker/entrypoint.sh`
  (`alembic upgrade head` → `exec region-price-monitor "$@"`) — миграции всегда применяются
  перед стартом любой команды; непривилегированный пользователь `app` (uid 1000), владеет
  `/srv/app` (включая `data/cookies`); `CMD ["serve"]` по умолчанию, любая другая команда CLI
  (`run-once`/`metrics`/`warm-ozon`/`healthcheck`/`import-*`) подставляется через
  `docker compose run app <команда>`.
- **`docker-compose.prod.yml`**: `postgres:16` с именованным volume `pgdata` и healthcheck;
  `app` (`build: .`, `env_file: .env`, `command: ["serve"]`, `restart: unless-stopped`,
  `depends_on: postgres healthy`) с именованным volume `cookies` на `COOKIE_STORE_DIR`
  (`/srv/app/data/cookies`) — прогретые куки Ozon переживают рестарт. Postgres **не
  публикуется наружу** (нет `ports:`). Дев-`docker-compose.yml` не тронут.
- **`Makefile`** — тонкие targets (`build`/`up`/`down`/`migrate`/`run-once`/`warm-ozon`/
  `metrics`/`logs`), только обёртка над `docker compose -f docker-compose.prod.yml`, без
  логики.
- **`docs/OPS.md`** (RU) — раннбук: клон → `.env` (в т.ч. `DATABASE_URL` хост `postgres` для
  прод-compose, `POSTGRES_USER/PASSWORD/DB`) → `build`/`up` → миграции (авто через entrypoint)
  → импорт справочников → смоук `run-once`/`metrics` без реального маркетплейса → ручной
  прогрев кук Ozon (`MANUAL=1 ... warm-ozon`, headful-шаг, ADR-0006 открытый вопрос) → боевой
  `serve` → чтение логов/метрик → volumes (`pgdata`/`cookies`) → обновление (`pull` → `build`
  → миграции на entrypoint). Явный copy-paste чеклист «боевой прогон».
- **`.env.example`**: добавлены `POSTGRES_USER/PASSWORD/DB`, `DATABASE_URL` переведён на хост
  `postgres` (прод-ориентированный дефолт), пояснение к `COOKIE_STORE_DIR` про volume.
- **`docs/adr/0008-script-shell-separation.md`** — зафиксировано решение владельца (только
  документация, без реализации): разложить исполняемую логику на самостоятельные Python-
  скрипты (control-panel, parameters, health, wb/ozon, orchestrator), оболочка (панель/CLI)
  — только I/O и управление; редактор скриптов панели (Фаза 8) получит пайплайн-конструктор
  в духе GitHub Actions. Статус: принято, не реализовано.
- **Не делали в этом слайсе** (см. BACKLOG «Потом»): zip-автоустановщик (ADR-0006), финальный
  выбор хостинга (открытый вопрос остаётся), реструктуризация `app/*` под ADR-0008.
- `docker/entrypoint.sh` переведён на `#!/bin/bash` (`set -o pipefail` не поддерживается
  `sh` в этом образе — падал на первом же запуске).
- DoD-гейт зелёный (Python-логика не менялась — ruff/mypy/pytest без изменений в `app`).
  **Живая проверка в песочнице (Docker доступен):** `docker compose -f docker-compose.prod.yml
  build` — зелёный; `healthcheck`/`run-once`/`metrics` вызваны как команда контейнера —
  entrypoint применяет `alembic upgrade head` и exec'ает команду; `import-regions`/
  `import-products` на демо-справочниках (`data/seed/*.json`) — идемпотентны; `run-once`
  прошёл полный цикл (6 попыток, `error_rate=1.0` — демо-SKU не существуют на реальном WB,
  ожидаемо для смоука без реального маркетплейса); `metrics --last` печатает сводку и
  Prometheus-текст; контейнер `app` работает под непривилегированным `uid=1002(app)`; volumes
  `pgdata`/`cookies` создаются и удаляются вместе с `down -v`. Полный «боевой» прогон против
  реальных WB/Ozon + реальных региональных прокси — по-прежнему задача владельца (нет доступа
  к реальным прокси/сети маркетплейсов в песочнице).

## 2026-07-23 — Рефактор скриптов и оболочки (`prompt-09-script-shell-separation`, ADR-0008)

- **Структурный, поведенчески нейтральный рефакторинг** — вся бизнес-логика `app/cli.py`
  (`_run_healthcheck`/`_import_products`/`_import_regions`/`_measure_wb`/`_measure_ozon`/
  `_warm_ozon`/`_run_once`) вынесена в новый пакет `app/scripts/`: `parameters.py` (снэпшот
  `Settings` + фабрика сессий + endpoints, печать с маской секретов), `control_panel.py`
  (активный набор «товар × регион» — то же правило, что `_active_pairs`: WB все регионы, Ozon
  только с `ozon` в `geo`), `health.py` (`ProxyHealthService` + `is_stale`/`warm_if_stale`,
  `HealthReport`, `--fix`), `wb.py`/`ozon.py` (обёртка над `measure_pair`, включая
  интерактивный прогрев кук Ozon и путь «нужен прогрев — пропущено»), `orchestrator.py`
  (`Step`/`Pipeline` — топологический порядок по Кану поверх `parameters → control_panel →
  health → run_once`; сам замер не переизобретён — вызывает существующий
  `app.scheduler.runner.run_once`).
- Каждый скрипт работает и отдельно (`python -m app.scripts.<name>`), и под `app/cli.py` —
  теперь тонкой оболочкой: подкоманды (`healthcheck`/`import-products`/`import-regions`/
  `measure-wb`/`measure-ozon`/`warm-ozon`/`run-once`/`serve`/`metrics`) только парсят
  аргументы и форматируют вывод; `serve` планирует `orchestrator.run(mode=RunMode.SCHEDULED)`
  через существующий `Scheduler`. Команды/флаги/вывод/коды выхода не изменились —
  `docker-compose.prod.yml`/`Makefile` работают без правок.
- **`tests/test_measure_wb.py`** (патчит `app.cli.get_session`/`app.cli.WbCollector.collect`,
  зовёт `cli._measure_wb`) не тронут — `_measure_wb`/`_measure_ozon` в `cli.py` по-прежнему
  читают модульные имена `get_session`/`WbCollector`/`OzonCollector` в момент вызова и
  прокидывают их в `wb.run()`/`ozon.run()` как инжектируемые зависимости, так что патчи на
  `app.cli.*` продолжают работать без изменений в тесте.
- Новые тесты (без изменения существующих ассертов): `tests/test_scripts_parameters.py`,
  `tests/test_scripts_control_panel.py`, `tests/test_scripts_health.py` (юнит, без БД/сети/
  Playwright — стаб-хранилище кук и стаб-`ProxyHealthService.verdict`), `tests/test_scripts_wb.py`,
  `tests/test_scripts_ozon.py` (argv-смоук без БД + БД-тесты по схеме `test_runner.py`, скип
  без `TEST_DATABASE_URL`/`DATABASE_URL`), `tests/test_orchestrator.py` (чистый тест
  `Pipeline`-механизма — порядок по зависимостям, детект цикла/неизвестной зависимости — плюс
  БД-тест: `orchestrator.run()` даёт тот же `RunSummary`/метрики, что и `run_once` напрямую,
  включая Фазу-6 сценарий искусственного бана + алерт).
- **Вживую на локальном Postgres 16 (Docker) — 126 passed** (весь прежний набор +
  6 новых тестовых файлов, БД-тесты не скипнуты). В песочнице без `DATABASE_URL` — 85 passed,
  9 skipped (ожидаемо, DB-гейтед тесты).
- DoD-гейт (`ruff check`/`ruff format --check`/`mypy app`/`pytest`) зелёный.
- **`docs/adr/0008-script-shell-separation.md`** — статус обновлён на «принято, реализуется —
  структурная часть в prompt-09»; формат пайплайна (YAML/JSON) и редактор панели остаются
  Фазе 8.
- **Не делали в этом слайсе**: YAML/JSON-формат пайплайна, панель/FastAPI/UI (Фаза 8);
  изменение схемы БД, новых enum-значений, новых зависимостей.

## 2026-07-23 — Дочистка тонкой оболочки (`prompt-10-thin-shell-complete`, ADR-0008)

- **Завершили разделение из prompt-09**: последняя бизнес-логика, остававшаяся в `app/cli.py`,
  перенесена в скрипты. `import_products`/`import_regions` — теперь функции
  `app/scripts/control_panel.py` (+ подкоманды `import-products <file>`/`import-regions <file>`,
  дефолт — прежний `show`). `_warm_ozon` — теперь `health.warm(region_codes, …)` (+ подкоманда
  `warm [--region …]`). `_metrics` — новый скрипт `app/scripts/report.py` (назван так, чтобы не
  конфликтовать с `app/obs/metrics.py`); `--run`/`--last` резолвятся как раньше. `_run_healthcheck`
  — `parameters.healthcheck()` (+ `--check`). `_serve` — `orchestrator.serve(...)` (+ подкоманда
  `serve`); `app/scheduler/runner.py::Scheduler` расширен опциональным `job`-колбэком (по
  умолчанию — прежний `run_once`), так что `serve` планирует именно `orchestrator.run` — разовый
  и плановый прогон идут по одному и тому же пайплайну.
- **`app/cli.py` стал чистым диспетчером**: импортирует только argparse/asyncio,
  `configure_logging` и `app.scripts.*`; каждая подкоманда — однострочная делегация. Grep на
  `Repository`/`make_proxy_provider`/`get_session`/`measure_pair` в `cli.py` не находит ничего
  (закреплено тестом `test_cli_module_holds_no_business_logic`).
  Команды/флаги/вывод/коды выхода не изменились — `docker-compose.prod.yml`/`Makefile`/
  entrypoint работают без правок.
- **`tests/test_measure_wb.py`** — цель патчей сменилась с удалённых `app.cli.get_session`/
  `app.cli._measure_wb` на `app.scripts.wb.WbCollector.collect`/`wb_script.run(...,
  session_factory=...)`; ассерты не менялись.
- Новые/расширенные тесты (ассерты старых тестов не менялись): `test_scripts_control_panel.py`
  (`import_products`/`import_regions` + подкоманды), `test_scripts_health.py` (`warm(...)` по
  умолчанию и по `--region`, неизвестный регион → exit 1), `test_scripts_report.py` (новый —
  argv-смоук + БД-тест `--run`/`--last`/нет прогонов), `test_scripts_parameters.py`
  (`healthcheck()` + `--check`), `test_orchestrator.py` (чистый тест: `serve` планирует Scheduler
  с job'ом `orchestrator.run`, без реального sleep/блокировки), `tests/test_cli.py` (новый —
  каждая подкоманда `cli.main([...])` делегирует в соответствующий скрипт; `configure_logging`
  вызывается один раз).
- **В песочнице без `DATABASE_URL` — 105 passed, 10 skipped** (DB-гейтед тесты, ожидаемо).
  DoD-гейт (`ruff check`/`ruff format --check`/`mypy app`/`pytest`) зелёный.
- **`docs/adr/0008-script-shell-separation.md`** — статус обновлён на «реализовано (структурная
  часть) — вся исполнительская логика в `app/scripts/`, `cli.py` — чистый диспетчер»; pipeline
  YAML/JSON-формат и редактор панели остаются Фазе 8.
- **`docs/ARCHITECTURE.md`** §«Скрипты и оболочка» — добавлена таблица команда↔скрипт +
  standalone-инвокация для каждой команды; явно указано, что оболочка — необязательное удобство.
- **Не делали в этом слайсе**: YAML/JSON-формат пайплайна, панель/FastAPI/UI (Фаза 8); изменение
  схемы БД, новых enum-значений, новых зависимостей.

## 2026-07-23 — Фундамент панели + Дашборд (`prompt-11-panel-foundation`, Фаза 8.1)

- **`app/panel/`** — новое FastAPI-приложение (`create_app()`), server-rendered Jinja2 +
  минимальный vanilla JS (`panel.js` — progressive enhancement формы «Запустить сейчас», без
  Node-сборки, без внешнего CDN). Вкладочная оболочка (`base.html`): Панель управления, Куки,
  Параметры подключения, Редактор скриптов, Логи/история — только Панель управления реализована,
  остальные — заглушка «в разработке» (`placeholder.html`). Тема — placeholder в стиле Vector·OS,
  все цвета/радиусы на CSS-переменных (`panel.css`) — под замену на реальный бренд-бук (SPEC §9.1).
- **Дашборд** (`GET /`, `dashboard.html`): здоровье проекта (running/idle, последний прогон, доля
  успеха), таблица последних прогонов, последние цены на пару товар×регион, активные города
  (прокси-ref маскирован). Данные — через новый `app/panel/queries.py` (`recent_runs`,
  `latest_snapshots` — последний снэпшот на пару через коррелированный подзапрос) +
  `app.obs.metrics.compute_run_metrics` + `app.scripts.control_panel.run`. Добавлен
  `RunRepository.list_recent(limit)` (чтение).
- **`POST /run`** — фоновый вызов `app.scripts.orchestrator.run` через `BackgroundTasks`;
  простой in-process флаг `_run_state["running"]` защищает от параллельных прогонов (второй
  запрос получает «прогон уже выполняется», `orchestrator.run` не вызывается повторно).
- **Панель — оболочка (ADR-0008), не бизнес-логика**: `app/panel/` не импортирует
  коллекторы/прокси/куки напрямую — только репозитории (read-only), `app.obs.metrics`,
  `app.scripts.*`. Закреплено тестом-грепом (`measure_pair`/`WbCollector`/`OzonCollector`/
  `make_proxy_provider` отсутствуют в `app/panel/`).
- **`app/scripts/panel.py`** (`run(host, port)` — поднимает uvicorn; `main(argv)` — `--host`/
  `--port`) + подкоманда `panel` в `app/cli.py` (однострочная делегация, как остальные команды).
  `docker-compose.prod.yml` получил закомментированный опциональный сервис `panel`.
- Новые зависимости: `fastapi`, `uvicorn[standard]`, `jinja2` (runtime); `httpx` (dev, нужен
  `fastapi.testclient.TestClient`).
- Тесты (без сети/БД, `TestClient` + monkeypatch): `test_panel_dashboard.py` (рендер + секреты не
  попадают в HTML), `test_panel_run.py` (одиночный вызов `orchestrator.run`, защита от
  параллельных прогонов), `test_panel_placeholders.py` (4 заглушки), `test_scripts_panel.py`
  (`--help`-смоук + маршруты `create_app()`), `test_cli.py` — новый тест на делегацию `panel`.
  DoD-гейт зелёный (117 passed / 10 skipped без Postgres в песочнице); весь прежний набор тестов
  не изменён.
- **Документы**: `docs/ROADMAP.md` — секция «Фаза 8» со слайсами 8.1 (готово)–8.5 (блокированы
  открытыми вопросами SPEC §9); `docs/ARCHITECTURE.md` — панель добавлена в таблицу
  команда↔скрипт + описание «панель — оболочка»; `docs/TZ.md` «Не делаем» уже отражал решение
  владельца от 2026-07-22 (правка не потребовалась).
- **Не делали в этом слайсе**: Куки/Параметры подключения/Редактор скриптов/настройки городов
  (Фаза 8.2–8.5, частично блокированы SPEC §9); авторизация панели; шифрование секретов; изменение
  схемы БД, новых enum-значений.

## 2026-07-23 — Local-first движок, Postgres опционален (`prompt-12-local-first-engine`)

- Решение владельца: отсутствие Postgres не должно блокировать продукт. Оформлено как
  [ADR-0009](adr/0009-local-first-storage.md) — ревизия [ADR-0004](adr/0004-scheduling-runtime.md)
  (очередь-в-Postgres перестаёт быть единственным вариантом).
- **Storage seam**: `app/storage/base.py` — Protocol'ы репозиториев (`Product`/`Region`/`Run`/
  `MeasureQueue`/`Attempt`/`PriceSnapshot`) один в один с сигнатурами `app/repositories.py`, плюс
  `Storage`-бандл и `make_storage(settings)`. Два бэкенда: `app/storage/local.py` (плоские
  JSON/JSONL-файлы под `LOCAL_STATE_DIR`, атомарная запись temp+`os.replace`, монотонные id,
  деньги — строкой) и `app/storage/postgres.py` (тонкая обёртка над прежними репозиториями, без
  изменения логики).
- **Локальная очередь**: `app/queue/local.py` (`LocalTaskQueue`) рядом с `PgTaskQueue`;
  `app/queue/factory.py::make_task_queue(settings, storage)` выбирает по `storage_backend`.
  Задокументировано: `FOR UPDATE SKIP LOCKED` — гарантия конкурентности только у Postgres,
  локальный бэкенд не защищён от гонки между процессами (расчёт на один процесс/машину).
- **Движок целиком переведён на seam**: `app/scheduler/runner.py` (`run_once`/`_worker`),
  `app/collectors/measure.py`, скрипты `wb`/`ozon`/`control_panel`/`health`/`report`/
  `orchestrator`, `app/panel/queries.py`+`app/panel/app.py` — везде репозитории строятся через
  `make_storage(settings)`, очередь — через `make_task_queue`. `ProxyHealthService.verdict` и
  `compute_run_metrics` тоже читают через seam (`attempts.recent_for_proxy_ref`/`for_run`), а не
  прямым SQL — поведение идентично на обоих бэкендах.
- **Конфиг**: `storage_backend: str = "local"` (default) / `"postgres"`, `local_state_dir: str =
  "data/state"` в `app/config.py` + `.env.example`.
- **Docker**: `docker/entrypoint.sh` мигрирует (`alembic upgrade head`) только при
  `STORAGE_BACKEND=postgres`; на `local` — создаёт `LOCAL_STATE_DIR`. `docker-compose.prod.yml`:
  `postgres` за профилем `postgres` (не стартует без него), `app` работает автономно с volume
  `state`. `Makefile`: `make up` — без Postgres; `make up-postgres` — с профилем.
- **Тесты**: `tests/test_storage_local.py` (17 тестов — round-trip каждой repo-операции локально,
  без БД) и `tests/test_local_end_to_end.py` (5 тестов — импорт → `run_once` → метрики/health/
  control_panel на `storage_backend=local`, стаб-коллекторы, без Postgres). Существующие
  DB-gated тесты (`test_runner.py`/`test_orchestrator.py`/`test_metrics.py`/`test_proxy_health.py`/
  `test_scripts_wb.py`) адаптированы под новую сигнатуру (`PostgresStorage(session)` вместо
  голой сессии) — ассерты не менялись. Юнит-тесты без БД (`test_scripts_control_panel.py`/
  `test_scripts_health.py`/`test_panel_dashboard.py`) переключены на патчинг `Local*Repository`
  вместо SQLAlchemy-репозиториев, т.к. `local` — новый дефолт. DoD-гейт зелёный: 140 passed / 10
  skipped (без Postgres в песочнице).
- **Не делали в этом слайсе** (следующие): настраиваемые source/sink-адаптеры (CSV/Excel/БД) +
  маппинг полей — `prompt-13`; мастер настройки — `prompt-14`; хранилище секретов (снято для
  локального режима, SPEC §9.3); Postgres-путь не удалён, работает за тем же seam.

## 2026-07-23 — I/O-адаптеры: source/sink CSV/Excel/DB + маппинг (`prompt-13-io-adapters`)

- **I/O seam** (ADR-0010): `app/io/base.py` — `ProductSource`/`ResultSink` Protocol'ы,
  канонический словарь SPEC-panel §7 как единственная развязка; `app/io/factory.py` —
  `make_product_source(settings)`/`make_result_sink(settings)` по `kind`.
- **Четыре адаптера**: `json` (сегодняшний локальный импорт без изменений, дефолт), `csv`
  (`csv`-модуль), `xlsx` (**openpyxl**, новая зависимость; `path`/`sheet`/A1 `range`, локатор —
  имя заголовка или буква колонки), `db` (SQLAlchemy поверх произвольной таблицы, импорт
  ленивый — параллель `app/storage/postgres.py`, файловым бэкендам сеть не нужна).
- **Маппинг как данные** (`app/io/mapping.py`): `{canonical_field: locator}` из
  `config/io.json` (`settings.io_config_path`, опционален); `validate()` ловит отсутствующие
  обязательные поля и локаторы вне заголовка источника (съехавший лист); `preview(n=5)` —
  первые N замаппленных строк.
- **Скрипты**: `control_panel.py import-products`/`import-regions` — `file` стал опциональным
  позиционным аргументом (и в `cli.py`, и в собственном `main()`); без файла читают через
  сконфигурированный источник (`import_products_from_source`/`import_regions_from_source`).
  Новый `app/scripts/export.py` (`python -m app.scripts.export`, verb `export` в `cli.py`) —
  строит канонические строки результата из `price_snapshots` (+ join `products`/`regions`
  через storage seam) и пишет через сконфигурированный сток; `--preview` печатает первые
  строки; без стока — чистый no-op с сообщением.
- **Обратная совместимость подтверждена тестом**: `tests/test_io_json_backcompat.py`
  воспроизводит сегодняшний `import-products`/`import-regions` файловый путь один в один;
  существующие тесты `control_panel`/`cli` не менялись, кроме добавления новых кейсов.
- **Тесты**: `test_io_mapping.py`, `test_io_csv.py`, `test_io_xlsx.py`,
  `test_io_json_backcompat.py`, `test_io_factory.py` (без сети/БД), `test_io_db.py` (за гейтом
  `TEST_DATABASE_URL`, пропускается без Postgres), плюс новые кейсы в
  `test_scripts_control_panel.py`/`test_scripts_export.py`. DoD-гейт зелёный: 172 passed / 11
  skipped (без Postgres в песочнице).
- **Не делали в этом слайсе** (следующий): мастер настройки — `prompt-14`; UI вкладки
  «Параметры подключения» (Фаза 8.4); финализация списка ценовых полей (SPEC §9.5).

## 2026-07-24 — Города: функциональный блок + локальный стор настроек (`prompt-14-cities-tab`)

- **Приоритет пересмотрен владельцем** (2026-07-23): панель должна быть рабочей точкой ввода
  настроек, не read-only витриной. Этот слайс **отменяет** ранее запланированный `prompt-14`
  (мастер настройки — откладывается) и вместо этого делает первый функциональный кусок —
  блок «Города» на Дашборде (SPEC §3). [ADR-0011](adr/0011-local-settings-store.md).
- **Локальный стор** `app/scripts/cities.py` (`settings.city_config_path`, по умолчанию
  `config/cities.json`) — плоский JSON, атомарная запись (temp+`os.replace`, как в
  `app/storage/local.py`). Модель «общее + локальное переопределение»: `defaults` по WB/Ozon
  + список городов, каждый с `mode: inherit | override` на площадку. `list_effective()`
  резолвит и убирает отключённые пары (город × площадка) из рабочего набора целиком.
- **Движок переключён**: `app/scripts/control_panel.py::run` строит `WorkSet` через
  `cities.list_effective()` вместо прямого `parse_proxy_map(settings.proxy_map_json)`;
  `CitySettings` получил `marketplace_proxies` — прокси резолвится независимо для WB/Ozon
  одного города. Без файла `config/cities.json` — сидируется один раз из `regions` +
  `proxy_map_json`/интервалов, сохраняя прежнее поведение (`WB` — всегда все активные регионы,
  `Ozon` — только с гео `ozon`).
- **Панель**: `POST /cities` (добавить), `POST /cities/{code}/{mp}` (mode/enabled/proxy/interval,
  пустой прокси на сабмите не обнуляет сохранённый), `POST /cities/{code}/delete` (деактивация,
  история не трогается) — все тонкие обёртки над `app/scripts/cities.py` (ADR-0008). Дашборд
  показывает общий профиль read-only + раскрываемые карточки городов. `cli.py cities
  list|add|set|enable|disable|remove` — тот же стор из командной строки.
- **Ручная проверка** (`STORAGE_BACKEND=local`): поднял `panel`, добавил город, выставил Ozon
  override с прокси и отключил WB для `msk` через HTML-формы — `config/cities.json` отразил
  изменения; `control-panel show` показал `region=msk proxy=*** marketplaces=ozon` (WB пропал
  из набора, Ozon-прокси замаскирован).
- **Тесты**: `test_cities_store.py` (round-trip/effective-resolution/CRUD/seed, 10 кейсов),
  `test_panel_cities.py` (дашборд рендерит блок, все три роута мутируют файл, маскирование,
  keep-proxy-if-empty, 7 кейсов); `test_scripts_control_panel.py`/`test_panel_dashboard.py`
  адаптированы под новый резолв (не меняли семантику, только фейковые фикстуры). Добавлена
  рантайм-зависимость `python-multipart` (нужна FastAPI `Form(...)`). DoD-гейт зелёный:
  189 passed / 11 skipped.
- **Не делали в этом слайсе** (следующий): редактор общего профиля (`defaults`) и глобальный
  тумблер площадки — общий профиль пока read-only; куки/параметры-подключения-UI/логи —
  отдельные слайсы Фазы 8.

## 2026-07-24 — Куки: одна кнопка «Авторизоваться и собрать», авто-обход городов (`prompt-15-cookies-tab`)

- Владелец (2026-07-23) зафиксировал UX: **одна кнопка на площадку** — «Авторизоваться и
  собрать» — логин-раз, дальше поток сам обходит настроенные города. [ADR-0012](adr/0012-cookie-collection-ux.md).
- **`app/cookies/warm.py`**: WB добавлен как полноценный таргет прогрева наравне с Ozon
  (`_MARKETPLACE_WARM_URL`). Новая функция `warm_all(store, marketplace, cities, ...)` — один
  видимый Playwright-контекст на весь обход: Ozon авто-переключает город (`?city=`-переход
  переписывает региональную куку) и сохраняет `CookieBundle` на каждый город; WB сохраняет
  одну сессионную куку под служебным кодом `_session`. Капча — авто-детект по маркерам на
  странице + поллинг до очистки/таймаута (`_looks_like_captcha`/`_wait_out_captcha`) — без
  консольного `input()`; кооперативный `cancel`-токен + таймаут на шаг, чтобы зависший город
  не подвесил весь обход. `warm`/`warm_if_stale` не тронуты (аддитивно).
- **`app/scripts/cookies.py`** (новый): `collect(marketplace)` берёт эффективные города из
  `cities.list_effective` и запускает `warm_all`; `status()` — health по каждому bundle
  (valid/expiring/stale через `is_stale`, «expiring» — ≤25% TTL до протухания);
  `set_manual`/`clear` — ручная вставка/сброс. Работает и отдельно
  (`python -m app.scripts.cookies`), и через `cli.py cookies collect|status|set-manual|clear`.
- **Панель**: `GET /tab/cookies` — реальная вкладка (кнопки, живой прогресс, таблица здоровья,
  ручной редактор), заменяет плейсхолдер. `POST /cookies/{mp}/collect` стартует джобу в
  отдельном потоке (`asyncio.to_thread`, синхронный Playwright-вызов не блокирует event loop);
  `GET /cookies/status` — поллинг прогресса (JS в `panel.js` опрашивает раз в 1.5с, пока джоба
  идёт); `POST /cookies/{mp}/{city}` — ручная вставка cookie JSON; `POST
  /cookies/{mp}/{city}/clear` — сброс (mark-stale, отдельного delete у `CookieStore` нет).
- **Ручная проверка (документируется, не выполнена в песочнице — нужен локальный Windows +
  видимый браузер владельцем):** `STORAGE_BACKEND=local`, поднять `panel`, открыть «Куки»,
  нажать «Авторизоваться и собрать» для Ozon — залогиниться раз, поток обходит города и
  сохраняет куку на каждый, пауза на капче; таблица здоровья показывает свежие записи; WB —
  один проход без обхода городов.
- **Тесты**: `test_cookies_script.py` (`collect` Ozon сохраняет bundle на город через
  стаб-`warm_all`, `collect` WB — одну сессионную запись, `status` — границы
  valid/expiring/stale, `set_manual`/`clear` round-trip через tmp `cookie_store_dir`, 4 кейса);
  `test_panel_cookies.py` (вкладка рендерит кнопки+таблицу здоровья, `POST .../collect` стартует
  джобу и `GET /cookies/status` отражает прогресс через стаб `collect`, ручная вставка/сброс
  через `TestClient`, 3 кейса); `test_panel_placeholders.py` обновлён — «Куки» больше не
  плейсхолдер. Реальный видимый браузер — за гейтом `MANUAL=1`, не в CI. DoD-гейт зелёный:
  195 passed / 11 skipped.
- **Не делали в этом слайсе:** headless/Xvfb-прогрев на сервере без экрана (остаётся открытым
  вопросом, SPEC §9.2); параметры подключения/редактор скриптов/логи — отдельные слайсы Фазы 8.

## 2026-07-24 — Ozon: регион по запомненному адресу, ревизия ADR-0012 (`prompt-16-ozon-address-memory`)

- **Баг найден и исправлен:** `_switch_ozon_city` переключал город Ozon повторным заходом на
  `?city=<имя>` — неверная модель. Ozon берёт регион из куки, которая пишется только когда
  оператор выбирает адрес доставки в UI; свободное имя города нельзя надёжно смэппить в
  канонический адрес. Решение владельца: не гадать маппинг — захватить реальный выбор
  оператора один раз и запомнить, дальше чинить автоматически. Оформлено в
  [ADR-0013](adr/0013-ozon-address-memory.md) (ревизует ADR-0012 частично, пункт про `?city=`).
- **`app/cookies/base.py`**: `CookieBundle.address_label: str | None = None` — запомненный
  адрес доставки Ozon для города; `None` у WB (`_session`) и у старых bundle без поля
  (обратная совместимость). `FsCookieStore` сериализует/читает поле, `mark_stale` его сохраняет.
- **`app/cookies/warm.py`**: `_switch_ozon_city` (`?city=`-хак) удалён. Добавлены
  `_capture_ozon_address` (guided — поллит страницу, пока оператор не выберет адрес в видимом
  окне, читает выбранный лейбл) и `_select_saved_address` (auto — ведёт адресную книгу Ozon к
  совпадению по запомненному `address_label`; DOM/API адресной книги эмпирически
  неопределены, поэтому реализовано защитно — любая неудача даёт `AddressCaptureError`, шаг
  помечается `skipped`, а не тихо сохраняет неверный регион). `WalkCity`/`WalkStepResult`
  несут `address_label`. Капча-детект/опрос, таймаут-на-шаг, `cancel`, `launch_browser`-сид —
  не менялись.
- **`app/scripts/cookies.py`**: `collect(marketplace, force=False)` теперь guided — обходит
  только Ozon-города без запомненного адреса (или все — с `--force`); новый
  `refresh(marketplace)` — auto-починка: только города с протухшей кукой **и** запомненным
  адресом; `status()` отдаёт `address_label` в `CookieHealth`; `set_manual` может задать
  адрес. CLI: `cookies collect <mp> [--force]`, `cookies refresh <mp>`.
- **Панель**: таблица здоровья показывает запомненный адрес Ozon («адрес не задан», если
  пусто); новая кнопка «Обновить протухшие» (`POST /cookies/{mp}/refresh`) — та же
  джоба/поллинг-инфраструктура, что и у collect; форма ручной вставки куки для Ozon получила
  поле «Адрес доставки».
- **Ручная проверка (документируется, не выполнена в песочнице — нужен локальный Windows +
  видимый браузер владельцем):** `STORAGE_BACKEND=local`, панель → «Куки»: первый запуск для
  Ozon-города без адреса запускает guided-выбор (оператор выбирает адрес, дальше запоминается);
  повторный «Обновить протухшие» чинит протухшие города автоматически, браузер выходит на
  экран только на капчу; WB не изменился (один проход).
- **Тесты**: `tests/test_cookies_address.py` (новый, 7 кейсов) — guided `collect` записывает
  `address_label` на город, `collect` пропускает города с уже запомненным адресом,
  `collect(force=True)` перезахватывает все, `refresh` авто-выбирает запомненный адрес только
  для протухших городов (не трогает свежие), `refresh` пропускает города без адреса, WB
  `refresh` по-прежнему сохраняет одну сессионную запись без адреса; `tests/test_cookie_store.py`
  — bundle без `address_label` в JSON грузится как `None`; `tests/test_panel_cookies.py`
  обновлён — таблица показывает адрес, кнопка/роут «Обновить протухшие», ручная вставка
  адреса. Реальный видимый браузер — за гейтом `MANUAL=1`, не в CI. DoD-гейт зелёный:
  204 passed / 11 skipped.
- **Не делали в этом слайсе:** маппинг свободное-имя → канонический адрес Ozon (это и был баг);
  headless/серверная авто-починка (SPEC §9.2, открытый вопрос); шифрование кук/адресов;
  изменения в коллекторах WB/Ozon, парсере, прокси-слое, storage/IO seam, схеме стора городов.

## 2026-07-24 — Вкладка «Параметры подключения» (`prompt-17-connection-tab`)

- **UI поверх I/O-бэкенда** (ADR-0010, `prompt-13`): реальная вкладка «Параметры подключения»
  (SPEC-panel §5, Фаза 8.4), единственная точка ввода `config/io.json`. Оформлено в
  [ADR-0014](adr/0014-connection-tab.md).
- `app/scripts/connection.py` (новый, тонкий скрипт ADR-0008): `load`/`save` — атомарный
  раунд-трип `io.json`; `columns(endpoint, table=...)` — читает фактический заголовок
  csv/xlsx/db-таблицы для ещё не сохранённого endpoint (нет файла/таблицы ⇒ пустой список, не
  падение); `validate_source`/`validate_sink` — собирают все нарушения маппинга (не бросают);
  `preview_source` — первые N строк products/regions через новый публичный
  `app/io/factory.build_product_source`; `mask_database_url`/`resolve_database_url` — маска
  пароля + «пустой пароль на сохранении = оставить прежний» (тот же паттерн, что
  `cities.py::mask_proxy`/`keep_proxy_if_empty`).
- `app/io/factory.py` — добавлены публичные `build_product_source`/`build_result_sink`
  (обёртки над существующими `_build_*`), чтобы панель могла превью/валидировать
  несохранённый endpoint из формы. `make_*` не изменились.
- `app/panel/app.py` + `templates/connection.html`/`_connection_preview.html` — `GET
  /tab/connection` (четыре вертикальные закладки §5.1–5.4, предзаполнены из `io.json`,
  `database_url` маскирован), `POST /connection/{source,sink}` (сохраняют секцию),
  `POST /connection/preview` (валидация+предпросмотр посланного, необязательно
  сохранённого конфига). Поля маппинга — из `app/io/base.py`
  (`PRODUCT_FIELDS`/`REGION_FIELDS`/`RESULT_FIELDS`), обязательные помечены `*`. `connection`
  убран из `_PLACEHOLDER_TABS`.
- CLI: `region-price-monitor connection {show,validate,preview}`.
- **Ручная проверка** (`STORAGE_BACKEND=local`): xlsx-источник с валидным маппингом → превью
  показывает канонические строки; тот же маппинг с намеренно неверной колонкой → флажок
  «locators absent from source header»; csv-сток + маппинг результатов сохранены; `python -m
  app.scripts.export --preview` после сохранения не падает (пустой local-стор → нет строк, чисто).
- **Тесты**: `tests/test_connection_script.py` (13, round-trip, validate missing/shifted,
  preview csv+xlsx, columns, mask/resolve database_url, `build_*` совпадает с `make_*`),
  `tests/test_connection_script_db.py` (db-путь, за гейтом `TEST_DATABASE_URL`),
  `tests/test_panel_connection.py` (6, рендер пустой/предзаполненной формы, `POST
  /connection/{source,sink}` персистят, превью возвращает маппленные строки и флагует сдвиг).
  `tests/test_panel_placeholders.py` обновлён — `connection` больше не заглушка. DoD-гейт
  зелёный: 222 passed / 12 skipped.
- **Не делали в этом слайсе:** мастер настройки; изменения поведения адаптеров (только
  публичные `build_*`); хранилище секретов (`database_url` по-прежнему открытым текстом в
  `io.json`, маскируется только при отображении); другие вкладки (редактор скриптов, логи);
  общий профиль по умолчанию; новые канонические поля сверх `app/io/base.py`.
