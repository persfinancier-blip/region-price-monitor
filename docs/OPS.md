# OPS — эксплуатация region-price-monitor (Prizma)

Раннбук для оператора: от клона репозитория до боевого прогона на прод-контейнерах.
Контекст: [ROADMAP.md](ROADMAP.md) → Фаза 7, [ADR-0004](adr/0004-scheduling-runtime.md)
(планировщик), [ADR-0006](adr/0006-panel-and-delivery.md) (панель/установщик — ещё не
реализованы, см. ниже «Что не входит»).

## Что не входит в этот слайс

- **Автоустановщика нет.** Разворачиваем через `docker compose` вручную (см. ниже).
- **Финальный хостинг не выбран** — всё портируемо через контейнеры, запускается на
  любой машине с Docker.
- Прогрев кук Ozon в проде — ручной шаг (см. §5); headless-прогрев на Linux-сервере
  (Xvfb) — открытый вопрос ADR-0006, не решён в этом слайсе.

## 1. Клон и `.env`

```bash
git clone <repo> && cd region-price-monitor
cp .env.example .env
```

Заполнить в `.env`:

- `DATABASE_URL` — для прод-`compose` хост должен быть `postgres` (имя сервиса), не
  `localhost`: `postgresql+asyncpg://postgres:postgres@postgres:5432/region_price_monitor`.
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` — креды самого контейнера Postgres;
  должны совпадать с тем, что зашито в `DATABASE_URL`.
- `PROXY_MAP_JSON` — JSON `{код_региона: proxy_url}` для реальных региональных прокси.
- Пороги здоровья прокси/антибота (`PROXY_*`, `WB_MIN_INTERVAL_S`, `OZON_MIN_INTERVAL_S`,
  `REQUEST_JITTER_S`) — можно оставить дефолты для первого прогона.
- `ALERTER` / `ALERT_WEBHOOK_URL` — `log` по умолчанию; поставить `webhook` + URL, если
  нужен реальный алерт при просадке доли успеха.
- `COOKIE_STORE_DIR` — не менять (`data/cookies`); в проде это путь **внутри контейнера**,
  примонтированный на именованный volume `cookies` — прогретые куки Ozon переживают
  рестарт.

**Секреты никогда не коммитятся** — `.env` в `.gitignore`, в репозитории только
`.env.example`.

## 2. Поднять Postgres и собрать образ

```bash
make build
make up
```

`make up` поднимает `postgres` (именованный volume `pgdata`, healthcheck) и `app`
(команда по умолчанию — `serve`). Postgres **не публикуется наружу** — порт не
проброшен на хост, доступ только из сети compose.

Миграции применяются автоматически: `docker/entrypoint.sh` перед стартом любой команды
контейнера выполняет `alembic upgrade head` (идемпотентно) и только потом запускает
запрошенную команду.

Проверить вручную (опционально, entrypoint уже это сделал при старте `app`):

```bash
make migrate
```

## 3. Справочники — товары и регионы

```bash
docker compose -f docker-compose.prod.yml run --rm app import-regions /srv/app/<путь_в_образе_или_volume>.json
docker compose -f docker-compose.prod.yml run --rm app import-products /srv/app/<путь>.json
```

Файлы со списком регионов/товаров должны быть доступны внутри контейнера — либо
смонтировать локальную директорию (`docker compose run --rm -v $(pwd)/seed:/srv/app/seed app import-regions /srv/app/seed/regions.json`),
либо запускать импорт локально с тем же `DATABASE_URL` (см. `pyproject.toml` — пакет
ставится и вне контейнера).

## 4. Смоук без реального маркетплейса

Для проверки, что цепочка «очередь → воркер → БД» работает, **не обязательно** ходить в
реальный WB/Ozon — `run-once` разбирает то, что лежит в `measure_queue` после импорта
справочников:

```bash
make run-once
make metrics
```

`metrics` печатает человекочитаемую сводку последнего прогона (доля успеха/банов/ошибок).

## 5. Прогрев кук Ozon (ручной шаг)

Ozon требует прогретых кук на регион (ADR-0005). Прогрев — headful/интерактивный шаг
(решение капчи вручную), поэтому в этом слайсе делаем его **локально**, не в проде:

```bash
MANUAL=1 region-price-monitor warm-ozon --region <код_региона>
```

(без `--region` — прогрев по всем активным регионам). Прогретые куки лежат в
`COOKIE_STORE_DIR` (`data/cookies`) в формате `storage_state` на город/площадку.
Перенести полученную директорию `data/cookies` в volume прод-контейнера (например,
`docker cp` в volume или через bind-mount при первом запуске) — до тех пор, пока
headless-прогрев на сервере (Xvfb) не реализован (открытый вопрос ADR-0006).

Через `make`:

```bash
make warm-ozon
```

запускает прогрев **внутри прод-контейнера** — рабочий вариант, если на сервере есть
графическое окружение/Xvfb; иначе используйте локальный прогрев выше.

## 6. Боевой прогон

```bash
make up
```

`app` стартует с командой `serve` — APScheduler-демон, расписание берётся из
`SCHEDULE_CRON`. Контейнер поднимается с `restart: unless-stopped` — переживает падения
и рестарт хоста.

Проверка, что всё живо:

```bash
make logs
```

— структурные JSON-логи (`LOG_FORMAT=json`): `run.started`/`run.finished`,
`measurement` на каждую попытку, `proxy.cooldown` при остывающем прокси.

```bash
make metrics
```

— сводка последнего прогона (тот же вывод, что и в смоуке §4, но уже по реальным
данным).

## 7. Данные и volumes

- `pgdata` — данные Postgres (products, regions, runs, measure_queue, price_snapshots,
  attempts).
- `cookies` — прогретые Ozon-куки (`COOKIE_STORE_DIR` внутри контейнера).

Оба — именованные Docker volumes, не в образе. `docker compose -f docker-compose.prod.yml down`
(без `-v`) их не трогает.

## 8. Обновление

```bash
git pull
make build
make up
```

Миграции применяются автоматически при старте `app` (entrypoint). Явно вызывать
`make migrate` не обязательно, но безопасно (идемпотентно).

## 9. Чеклист «боевой прогон» (copy-paste)

- [ ] `.env` заполнен: `DATABASE_URL`/`POSTGRES_*` согласованы, `PROXY_MAP_JSON` — реальные
      региональные прокси, `ALERTER`/`ALERT_WEBHOOK_URL` настроены.
- [ ] `make build && make up` — `postgres` healthy, `app` запущен.
- [ ] `make migrate` (или проверить логи entrypoint) — `alembic upgrade head` прошёл.
- [ ] `import-regions` + `import-products` — реальные справочники загружены.
- [ ] Куки Ozon прогреты локально (`MANUAL=1 ... warm-ozon`) и перенесены в volume `cookies`.
- [ ] `make run-once` — прогон против реальных WB/Ozon + прокси завершился, `price_snapshots`
      пишутся.
- [ ] `make metrics` — доля успеха в норме, алерт не сработал (или сработал ожидаемо).
- [ ] `serve` (уже запущен через `make up`) — расписание `SCHEDULE_CRON` подтверждено по
      логам следующего запланированного прогона.
- [ ] `make logs` — структурные логи читаемы, ошибки/баны в пределах ожидаемого.
