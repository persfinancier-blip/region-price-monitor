# Архитектура — region-price-monitor (Prizma)

Документ описывает компоненты, потоки данных, модель данных и ключевые интерфейсы. Решения обоснованы в [ADR](adr/). Требования — в [TZ.md](TZ.md).

## Обзор

Сервис по расписанию берёт из PostgreSQL активные пары **(товар × регион)**, для каждой снимает цену через **headless-браузер + региональный прокси**, устойчиво проходя антибот, и пишет результат обратно в PostgreSQL как отдельную запись истории.

```
                 ┌───────────────┐
   cron/расписание│  Scheduler    │  создаёт run, ставит задачи в очередь
                 └──────┬────────┘
                        ▼
                 ┌───────────────┐        ┌──────────────────┐
                 │  TaskQueue    │◀──────▶│   PostgreSQL     │
                 │ (очередь в БД)│        │ products/regions │
                 └──────┬────────┘        │ runs/queue       │
                        ▼                 │ price_snapshots  │
                 ┌───────────────┐        │ attempts         │
                 │  Worker pool  │        └──────────────────┘
                 │ (asyncio)     │
                 └──────┬────────┘
          ┌─────────────┼──────────────┐
          ▼             ▼               ▼
   ┌────────────┐ ┌────────────┐ ┌──────────────┐
   │ProxyProvider│ │ Browser    │ │MarketplaceCol-│
   │(регион→IP) │ │ (Playwright│ │lector: WB/Ozon│
   └─────┬──────┘ │  +stealth) │ └──────┬───────┘
         ▼        └────────────┘        ▼
   коммерческий прокси            WB / Ozon (публичные цены)
```

## Компоненты

- **Scheduler** — по cron-выражению открывает `run` и наполняет очередь задачами-замерами по всем активным парам. MVP: APScheduler в процессе приложения ([ADR-0004](adr/0004-scheduling-runtime.md)).
- **TaskQueue** — интерфейс очереди; MVP-реализация поверх таблицы в Postgres (`FOR UPDATE SKIP LOCKED`). Позже — Redis/Arq без смены коллекторов.
- **Worker pool** — исполнители замеров с ограниченной конкурентностью браузерных контекстов; горизонтально масштабируется несколькими контейнерами.
- **ProxyProvider** — выдаёт региональный прокси и принимает исход попытки; инкапсулирует вендора и политику здоровья/ротации ([ADR-0003](adr/0003-proxy-provider.md)).
- **Browser** — обёртка над Playwright: stealth-настройка контекста, геопривязка, перехват нужных сетевых ответов, детект капчи/бана.
- **MarketplaceCollector** — интерфейс парсера цены; реализации `WbCollector` и `OzonCollector`. Изолируют хрупкую логику селекторов/эндпоинтов ([ADR-0002](adr/0002-scraping-strategy.md)).
- **Repository / storage** — SQLAlchemy-репозитории поверх Postgres; Alembic-миграции.
- **CLI** — импорт справочников (товары/регионы), ручной запуск прогона, обслуживание.
- **Observability** — структурные логи; метрики прогонов (успех/бан/ошибки), Prometheus на фазе устойчивости.

## Поток одного замера

1. Worker берёт задачу `(product_id, region_id, run_id)` из очереди.
2. `ProxyProvider.acquire(region)` → аренда прокси нужного региона.
3. Browser поднимает stealth-контекст с этим прокси и гео-параметрами региона.
4. `MarketplaceCollector.collect(product, region, page)` → цена, цена без скидки, цена «с картой», наличие, raw.
5. При капче/бане: `ProxyProvider.report(hard_ban)`, ретрай с backoff через другой прокси (до лимита попыток).
6. Успех: запись в `price_snapshots` + `attempts`; `ProxyProvider.report(ok)`.
7. Финализация `run`: агрегирующая статистика (успех/ошибки/баны).

## Модель данных (PostgreSQL)

Ориентир схемы (детали фиксируются миграцией в фазе 1):

- **products** — `id`, `marketplace` (enum: `wb`|`ozon`), `sku` (артикул), `url`, `name`, `is_active`, `created_at`. Уник: (`marketplace`, `sku`).
- **regions** — `id`, `code` (напр. `msk`, `spb`), `name`, `geo` (jsonb: параметры под каждый маркетплейс — WB `dest`, Ozon город/координаты/адрес), `is_active`.
- **runs** — `id`, `mode` (`scheduled`|`manual`), `started_at`, `finished_at`, `stats` (jsonb: total/ok/failed/banned), `status`.
- **measure_queue** — `id`, `run_id`, `product_id`, `region_id`, `status` (`pending`|`in_progress`|`done`|`failed`), `attempts`, `locked_at`. Основа очереди-в-БД.
- **price_snapshots** — `id`, `product_id`, `region_id`, `run_id`, `captured_at`, `price`, `price_base` (без скидки), `price_card` (кошелёк/картой), `currency`, `is_available`, `raw` (jsonb). История — только вставки, без апдейтов.
- **attempts** — `id`, `queue_id`, `proxy_ref`, `outcome` (`ok`|`soft_ban`|`hard_ban`|`timeout`|`error`), `error`, `duration_ms`, `created_at`. Диагностика антибота и прокси.

Индексы под типовые выборки: `price_snapshots (product_id, region_id, captured_at desc)`; `measure_queue (status, run_id)`.

## Storage seam: local-first, Postgres опционален ([ADR-0009](adr/0009-local-first-storage.md))

Модель данных выше — это форма (products/regions/runs/measure_queue/price_snapshots/attempts),
не обязательно физическая таблица Postgres. Движок обращается к данным только через
Protocol-репозитории (`app/storage/base.py`), собираемые фабрикой
`make_storage(settings) -> Storage`:

- **`local`** (`storage_backend=local`, по умолчанию) — `app/storage/local.py`: те же сущности
  плоскими файлами под `settings.local_state_dir` (`products.json`/`regions.json`/`queue.json` —
  весь файл целиком upsert'ится; `runs.jsonl`/`attempts.jsonl`/`snapshots.jsonl` — append-only).
  Запись — temp-файл + `os.replace` (атомарно); id — монотонный локальный счётчик на сущность.
  Деньги (`price`/`price_base`/`price_card`) сериализуются как строка, не float.
- **`postgres`** (`storage_backend=postgres`) — `app/storage/postgres.py`: тонкая обёртка над
  прежними SQLAlchemy-репозиториями (`app/repositories.py`), без изменения логики.

`TaskQueue` (очередь задач) следует тому же правилу: `make_task_queue(settings, storage)`
возвращает `LocalTaskQueue` (`app/queue/local.py`, поверх локального стора) или `PgTaskQueue`
(`app/queue/postgres.py`, `FOR UPDATE SKIP LOCKED`) по тому же переключателю. **`SKIP LOCKED` —
гарантия конкурентности только у Postgres-бэкенда**: `LocalTaskQueue` не защищена от гонки между
независимыми процессами — предполагается один процесс/одна машина (локальный однопользовательский
сценарий).

Оба бэкенда дают идентичное поведение движку: `run_once`/`orchestrator`, скрипты
`wb`/`ozon`/`control_panel`/`health`/`report`, панель — все строят репозитории и очередь через эти
две фабрики, ни разу не создавая SQLAlchemy-сессию напрямую. `ProxyHealthService.verdict` и
`compute_run_metrics` тоже читают через seam (`attempts.recent_for_proxy_ref`/`attempts.for_run`),
а не прямым SQL — поэтому работают одинаково на обоих бэкендах.

Docker: `docker/entrypoint.sh` запускает `alembic upgrade head` только при
`STORAGE_BACKEND=postgres`; на `local` — создаёт `LOCAL_STATE_DIR` и пропускает миграции.
`docker-compose.prod.yml` держит `postgres` за профилем `postgres` — `app` работает автономно.

Осознанно не входит в этот слайс (следующий слайс): мастер настройки (`prompt-14`) поверх
I/O seam ниже.

## I/O seam: настраиваемые source/sink-адаптеры + маппинг ([ADR-0010](adr/0010-io-adapters.md))

Источник списка товаров/регионов и приёмник результатов измерений — тоже Protocol-based seam
(`app/io/base.py`: `ProductSource`, `ResultSink`), зеркальный storage seam выше, но по другой
оси: не «где живёт внутреннее состояние движка», а «откуда приходит справочник и куда пишутся
результаты». Обе стороны говорят только на **каноническом словаре** (SPEC-panel §7:
`marketplace, sku, url, name, region, price, price_no_card, price_card, currency,
availability, measured_at, status`) — адаптер переводит его в свой формат и обратно.

`make_product_source(settings)` / `make_result_sink(settings)` (`app/io/factory.py`) выбирают
адаптер по `kind` (`json` | `csv` | `xlsx` | `db`), сконфигурированному в `config/io.json`
(`settings.io_config_path`; пример — `config/io.example.json`): `json` — сегодняшний локальный
импорт без маппинга (ключи уже канонические, обратная совместимость); `csv`/`xlsx` — файлы с
маппингом `canonical -> заголовок/буква колонки` (`app/io/mapping.py`: `validate()` ловит
отсутствующие обязательные поля и съехавшие колонки, `preview()` — первые N замаппленных строк);
`db` — произвольная таблица источника/результата через SQLAlchemy, импорт ленивый (та же
опциональность, что у `app/storage/postgres.py`). Нет `config/io.json` ⇒ `json`-источник, сток
не настроен (локально-по-умолчанию, как и storage seam).

`control_panel.py import-products`/`import-regions` читают через сконфигурированный источник,
когда явный файл не передан; `app/scripts/export.py` (`export` verb в `cli.py`) строит
канонические строки результата из `price_snapshots` (+ join через storage seam) и пишет через
сконфигурированный сток, с `--preview` для сухого прогона.

Осознанно не входит в этот слайс: мастер настройки (`prompt-14`), финализация списка ценовых
полей (SPEC §9.5 — маппинг спроектирован так, чтобы список рос без изменений кода адаптеров).

### Вкладка «Параметры подключения» ([ADR-0014](adr/0014-connection-tab.md))

UI поверх этого seam'а (Фаза 8.4, SPEC-panel §5): `app/scripts/connection.py` — тонкий скрипт
(ADR-0008), `load`/`save` для `io.json` (атомарно), `columns`/`validate_source`/`validate_sink`
(валидация маппинга против реального заголовка источника/приёмника, не бросает — возвращает
список нарушений) и `preview_source` (первые N строк, работает и для ещё не сохранённого
конфига через новые публичные `app/io/factory.build_product_source`/`build_result_sink`).
`GET /tab/connection` + `POST /connection/{source,sink,preview}` (`app/panel/app.py`,
`templates/connection.html`) — четыре вертикальные закладки §5.1–5.4, поля маппинга берутся
из `PRODUCT_FIELDS`/`REGION_FIELDS`/`RESULT_FIELDS` (`app/io/base.py`, единственный словарь).
`database_url` маскируется при отображении, пустой пароль на сохранении оставляет прежний
(тот же паттерн, что прокси в Городах, ADR-0011) — секретов по-прежнему нет (ADR-0009).

## Ключевые интерфейсы (эскиз)

```python
class MarketplaceCollector(Protocol):
    marketplace: Marketplace
    async def collect(self, product: Product, region: Region, page: Page) -> PriceSnapshot: ...

class ProxyProvider(Protocol):
    async def acquire(self, region: RegionCode) -> ProxyLease: ...
    async def report(self, lease: ProxyLease, outcome: Outcome) -> None: ...

class TaskQueue(Protocol):
    async def enqueue(self, run_id: int, pairs: list[Pair]) -> None: ...
    async def claim(self, limit: int) -> list[QueueItem]: ...   # FOR UPDATE SKIP LOCKED
    async def complete(self, item: QueueItem, outcome: Outcome) -> None: ...
```

## Устойчивость к антиботу (сводка)

- Реалистичный фингерпринт браузера + консистентные UA/locale/timezone под регион.
- Ротация прокси и «остывание» забаненных через `ProxyProvider`.
- Ретраи с экспоненциальным backoff; лимит попыток на замер; детект капчи/бана.
- Человекоподобный темп и ожидание сетевых ответов вместо «сырых» запросов.
- Пер-маркетплейсные лимиты частоты; изоляция сбоя одного замера от прогона.

## Скрипты и оболочка (ADR-0008)

Исполняемая логика полностью разложена на самостоятельные модули `app/scripts/*` — каждый
работает headless сам по себе (`python -m app.scripts.<name> …`) и не зависит от `app/cli.py`;
оболочка — необязательное удобство, а не зависимость:

- **`parameters`** — резолвит `Settings` + фабрику сессий + адреса (WB card URL, Ozon API URL,
  `COOKIE_STORE_DIR`) в один типизированный снэпшот `Parameters`; печатает их с маской на секретах.
  `--check` вместо этого проверяет доступность стора: на `local` — что `LOCAL_STATE_DIR`
  доступен на запись, на `postgres` — `app.db.healthcheck` (`SELECT 1`); возвращает код выхода.
- **`control_panel`** — активный набор «товар × регион», резолвится через
  `app/scripts/cities.py::list_effective()` (ADR-0011): пара (город, площадка) с `enabled=false`
  выпадает из набора целиком, прокси резолвится независимо для WB/Ozon. Подкоманды
  `import-products <file>` / `import-regions <file>` заливают справочники из JSON (upsert); без
  подкоманды (или `show`) — печатает активный рабочий набор.
- **`cities`** — локальный стор «Города» (`config/cities.json`, ADR-0011): общий профиль
  (`defaults`) по WB/Ozon + список городов с `mode: inherit | override` на каждую площадку.
  `list_effective()` резолвит inherit/override и убирает отключённые пары. Без файла — сидирует
  один раз из `regions` + `proxy_map_json`/интервалов (прежнее поведение сохраняется). Панель
  (`POST /cities*`) и CLI (`cities add|set|enable|disable|remove`) — тонкие обёртки над ним.
- **`health`** — здоровье прокси (`ProxyHealthService`) и свежесть кук Ozon (`is_stale`); при
  `--fix`/`fix=True` протухшие куки перегреваются через `warm_if_stale`. Подкоманда
  `warm [--region …]` прогревает куки Ozon для одного или всех регионов напрямую.
- **`wb` / `ozon`** — замер одной или всех активных пар через `measure_pair`; воспроизводят
  прежнее поведение `measure-wb`/`measure-ozon` (включая интерактивный прогрев кук Ozon и путь
  «нужен прогрев — пропущено» вне интерактивного режима) один в один.
- **`report`** — печатает метрики прогона (`--run <id>` или `--last`): человекочитаемая строка +
  Prometheus-текст (`app/obs/metrics.py`), плюс структурный лог `metrics`. Назван `report`, чтобы
  не конфликтовать с `app/obs/metrics.py`.
- **`orchestrator`** — собирает пайплайн `parameters → control_panel → health → run_once`:
  небольшая `Step`/`Pipeline`-структура в коде исполняет шаги в порядке зависимостей
  (топологическая сортировка), но сам замер (очередь/пул воркеров/ретраи/алерт) не
  переизобретает — вызывает существующий `app.scheduler.runner.run_once`. Этот шов рассчитан
  на то, что в Фазе 8 жёстко зашитый список шагов можно будет заменить YAML/JSON-описанием
  без изменения самих скриптов — редактор скриптов панели (SPEC-panel §6) станет
  конструктором такого пайплайна. Подкоманда `serve` запускает cron-демон (APScheduler),
  планирующий `orchestrator.run(mode=RunMode.SCHEDULED)` — тот же пайплайн, что и разовый
  прогон; без подкоманды — один проход пайплайна (эквивалент `run-once`).
- **`panel`** — поднимает локальную веб-панель (uvicorn + `app.panel.create_app`, Фаза 8.1,
  [SPEC-panel.md](SPEC-panel.md)). Панель — **ещё одна оболочка** над скриптами (как и
  `app/cli.py`): `app/panel/` не содержит бизнес-логики, только read-only-запросы
  (`app/panel/queries.py`, репозитории, `app.obs.metrics`) и делегирование действий
  («Запустить сейчас» → `orchestrator.run` фоновой задачей). Server-rendered (Jinja2 +
  минимальный JS, без Node-сборки); только `127.0.0.1`, без авторизации (SPEC §9.6 — позже).

### Соответствие команда ↔ скрипт

| Команда CLI      | Скрипт                             | Отдельный запуск                                           |
|-------------------|-------------------------------------|-------------------------------------------------------------|
| `healthcheck`     | `app.scripts.parameters`           | `python -m app.scripts.parameters --check`                  |
| `import-products` | `app.scripts.control_panel`        | `python -m app.scripts.control_panel import-products <file>`|
| `import-regions`  | `app.scripts.control_panel`        | `python -m app.scripts.control_panel import-regions <file>` |
| `cities`          | `app.scripts.cities`               | `python -m app.scripts.cities [list\|add\|set\|enable\|disable\|remove]` |
| `cookies`         | `app.scripts.cookies`              | `python -m app.scripts.cookies [collect\|refresh\|status\|set-manual\|clear]` |
| `measure-wb`      | `app.scripts.wb`                   | `python -m app.scripts.wb [--region …] [--sku …]`            |
| `measure-ozon`    | `app.scripts.ozon`                 | `python -m app.scripts.ozon [--region …] [--sku …]`          |
| `warm-ozon`       | `app.scripts.health`               | `python -m app.scripts.health warm [--region …]`             |
| `run-once`        | `app.scripts.orchestrator`         | `python -m app.scripts.orchestrator`                         |
| `serve`           | `app.scripts.orchestrator`         | `python -m app.scripts.orchestrator serve`                  |
| `metrics`         | `app.scripts.report`               | `python -m app.scripts.report --run <id> \| --last`          |
| `panel`           | `app.scripts.panel`                | `python -m app.scripts.panel [--host …] [--port …]`          |

`app/cli.py` — **чистый диспетчер**: импортирует только argparse/asyncio, `configure_logging` и
`app.scripts.*`; каждая подкоманда — однострочная делегация в скрипт (парсинг аргументов +
форматирование вывода, без обращений к репозиториям/провайдерам/сессиям/коллекторам напрямую).
Команды/флаги/вывод/коды выхода не изменились — `docker-compose.prod.yml`/`Makefile`/entrypoint
продолжают работать без правок. Владелец может не использовать оболочку вовсе — любой скрипт
запускается автономно.

## Конфигурация и секреты

Всё через окружение (pydantic-settings): DSN Postgres, креды/endpoint прокси-провайдера, cron-расписание, порог конкурентности, лимиты ретраев. Секреты — только в `.env`/секрет-хранилище, никогда в репозиторий (форма — в `.env.example`).

## Что осознанно отложено

Гибридный API-путь как оптимизация ([ADR-0002](adr/0002-scraping-strategy.md)), внешний брокер очереди и выбор прод-хостинга ([ADR-0004](adr/0004-scheduling-runtime.md)), дашборд/визуализация поверх данных.
