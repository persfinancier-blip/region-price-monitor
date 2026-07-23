# BACKLOG — region-price-monitor

Очередь задач. Пополняется Cowork'ом и владельцем; вычёркивается по факту мержа.
Слайсы и DoD — в [docs/ROADMAP.md](docs/ROADMAP.md).

## Сейчас

- [x] **Фаза −1 — Спайк осуществимости** — ✅ **GO** (2026-07-22). WB через `requests`; Ozon добит: куки + `curl_cffi` (ADR-0005); регион — в куках.
- [x] **Фаза 0 — Скелет и тулинг** (`prompt-01-skeleton`) — DoD-гейт зелёный, `docker compose up` + `alembic upgrade head` + `cli healthcheck` проверены вживую.
- [x] **Фаза 1 — Модель данных и миграции** (`prompt-02-schema`) — миграция применяется/откатывается вживую на Postgres 16; CLI-импорт справочников идемпотентен; тесты репозиториев зелёные (`TEST_DATABASE_URL`).
- [x] **Фаза 2 — Коллектор WB, один регион, без прокси** (`prompt-03-wb-collector`) — DoD-гейт зелёный; `parse_wb_card` покрыт юнит-тестами на закоммиченном сэмпле (без сети). Живая проверка `measure-wb` против реального WB + Postgres не выполнена в песочнице — нужна ручная проверка владельцем.
- [x] **Фаза 3 — Регионализация + ProxyProvider** (`prompt-04-regions-proxy`) — DoD-гейт зелёный; `ProxyProvider` + `StaticProxyProvider` (провайдер-агностично), классификатор исходов, `measure-wb` пишет `measure_queue`+`attempts` по всем активным регионам. Живая проверка с реальным `proxy_map_json` (регион-разные цены) не выполнена в песочнице — нужна ручная проверка владельцем.
- [x] **Фаза 4 — Коллектор Ozon** (`prompt-05-ozon-collector`) — DoD-гейт зелёный; `OzonCollector` (`curl_cffi` + `impersonate="chrome"` + прогретые куки), `FsCookieStore` + `CookieWarmer` (Playwright, `MANUAL=1`), гибридная модель регион-по-куке/прокси-по-желанию (ADR-0005), `measure-ozon`/`warm-ozon`. Живая проверка (два города, разные `cardPrice` по кукам) не выполнена в песочнице — нужна ручная проверка владельцем.
- [x] **Фаза 5 — Оркестрация и расписание** (`prompt-06-orchestration`) — DoD-гейт зелёный (61 passed вживую на Postgres); `TaskQueue`/`PgTaskQueue` (`SKIP LOCKED`, конкурентный `claim` проверен тестом), общий `measure_pair`, ретраи с backoff, worker pool, `Scheduler`(APScheduler) + `run-once`/`serve`. Живая проверка `run-once` на локальном Postgres прошла полный цикл; сетевой сценарий (реальные WB/Ozon через прокси) не выполнен в песочнице — нужна ручная проверка владельцем.
- [x] **Фаза 6, часть 1 — Наблюдаемость** (`prompt-07-observability`) — DoD-гейт зелёный (83 passed вживую на Postgres); структурные JSON-логи (`app/obs/logging.py`, per-attempt `measurement` + `run.started`/`run.finished`), метрики из `runs`/`attempts` без новой схемы (`app/obs/metrics.py`, `metrics` CLI — человекочитаемо + Prometheus text), `Alerter`-сиим (`app/obs/alerts.py` — `LogAlerter`/`WebhookAlerter`, порог доли успеха ≥0.9 по TZ). Живая проверка на локальном Postgres пройдена (структурные логи + алерт при доле успеха 0 < 0.9 подтверждены). ADR-0007.
- [x] **Фаза 6, часть 2 — Здоровье прокси/cooldown + антибот-тюнинг** (`prompt-08-proxy-health`) — DoD-гейт зелёный (105 passed вживую на Postgres); `HealthAwareProxyProvider` (декоратор над `ProxyProvider`, ADR-0003) выводит cooldown из `attempts` без новой схемы, `ProxyOnCooldown` → чистый скип без фейкового attempt (`app/proxy/health.py`); общий на пул `RateLimiter` — мин. интервал + джиттер на маркетплейс (`app/collectors/pacing.py`); консистентный по региону fingerprint — WB-заголовки/Ozon `impersonate` (`app/collectors/fingerprint.py`). ROADMAP/prompts-README приведены в соответствие с разбивкой Фазы 6.
- [x] **Фаза 7, часть 1 — Deploy core** (`prompt-ops-01-deploy`) — прод-`Dockerfile` (non-root, entrypoint = `alembic upgrade head` + `exec`), `docker-compose.prod.yml` (postgres не публикуется наружу, именованные volumes `pgdata`/`cookies`), `Makefile` (build/up/down/migrate/run-once/warm-ozon/metrics/logs), `docs/OPS.md` (раннбук + чеклист боевого прогона). Установщик и выбор хостинга — не входят, см. «Потом». `docs/adr/0008-script-shell-separation.md` зафиксирован (принято, не реализовано).
- [x] **Рефактор — разделение скриптов и оболочки** (`prompt-09-script-shell-separation`, ADR-0008) — бизнес-логика `app/cli.py` вынесена в `app/scripts/{parameters,control_panel,health,wb,ozon,orchestrator}` (каждый запускается и отдельно, и под `cli.py`); `orchestrator` собирает `Step`/`Pipeline` (`parameters → control_panel → health → run_once`), переиспользуя `run_once` без переизобретения пула/очереди/ретраев/алерта; `app/cli.py` — тонкая оболочка, команды/флаги/вывод/коды выхода не изменились. DoD-гейт зелёный; вживую на Postgres — 126 passed. ADR-0008 статус: «принято, реализуется — структурная часть в prompt-09».

## Потом
- [ ] Фаза 7, часть 2 — **zip-автоустановщик** под Windows/Linux (`prompt-ops-02`) — ADR-0006.
- [ ] Выбор хостинга прода — открытый вопрос, снимается перед реальным разворачиванием (см. «Открытые вопросы»).
- [ ] **Фаза 8 — Панель управления** (FastAPI, стиль «Вектор·OS»): дашборд, города (наследование+переопределение), куки, маппинг, редактор скриптов, логи — SPEC-panel, ADR-0006. Редактор скриптов реализуется с учётом [ADR-0008](docs/adr/0008-script-shell-separation.md) (скрипты + пайплайн в духе GitHub Actions).

## Открытые вопросы (снять до соответствующей фазы)

- [ ] Выбрать провайдера прокси — интерфейс-первый подход принят (ADR-0003): `ProxyProvider` + `StaticProxyProvider` уже в коде (Фаза 3); коммерческий провайдер (любой) добавляется как ещё одна реализация, не блокирует дальнейшие фазы.
- [x] **Уточнить масштаб (SKU × регионы × частота)** — удовлетворено для MVP выбором очереди-в-Postgres (Фаза 5, ADR-0004): `TaskQueue` — чистый seam, внешний брокер (Redis/Arq) подключается позже без переписывания коллекторов, если объём вырастет.
- [ ] Выбрать хостинг прода — остаётся открытым; deploy-core (Фаза 7, часть 1) намеренно портируем (docker compose), решение о конкретном хостинге не блокирует запуск/тест.
- [ ] Финальный список регионов и их гео-параметры.
- [ ] Полный список нужных ценовых полей (базовая / скидка / картой / Premium).
- [x] **Определить региональную куку Ozon** — решение (owner, 2026-07-23): не выделять одну куку, хранить **полный прогретый набор** на город (ADR-0005).
- [ ] **Измерить срок жизни кук Ozon** — конфиг `ozon_cookie_ttl_hours` (по умолчанию 12ч, time-based) заведён; реальный TTL предстоит измерить на живом прототипе.
- [ ] **Прогрев кук на Linux-сервере** (локально+перенос vs Xvfb) — до фазы 7/8.
- [ ] **Шифрование секретов** в панели (куки/пароли/прокси) — до фазы 8.
