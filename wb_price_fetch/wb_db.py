"""Источник и приёмник данных — SQL. Города и артикулы читаются из таблиц, результат пишется в таблицу.

Самодостаточный модуль: PostgreSQL через psycopg (2 или 3), SQLite — для локальной проверки
без сервера. Схему таблиц не навязывает: имена колонок определяются автоматически из
нескольких общепринятых вариантов, поэтому подходит и к уже существующим таблицам.

Строка подключения:
    postgresql://user:pass@host:5432/dbname
    sqlite:///путь/к/файлу.db
    либо переменные окружения PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD

Ожидаемые колонки (любой из вариантов, регистр не важен):

    таблица городов:  code|city_code|city   name|city_name   lat|latitude   lon|longitude|lng
                      dest       — необязательно; если есть, гео-API не дёргается
                      is_active|active — необязательно; фильтр

    таблица SKU:      sku|nm|nm_id|article    marketplace — необязательно, фильтруется по 'wb'
                      is_active|active — необязательно

Таблица результатов создаётся сама, если её нет.
"""

from __future__ import annotations

import os
import re
from typing import Any, Sequence
from urllib.parse import urlsplit

__all__ = [
    "connect",
    "load_cities",
    "load_skus",
    "save_results",
    "DbError",
]


class DbError(RuntimeError):
    """Ошибка работы с базой."""


# Варианты имён колонок: первый найденный выигрывает.
CITY_COLUMNS = {
    "code": ("code", "city_code", "city", "region_code"),
    "name": ("name", "city_name", "title", "region_name"),
    "lat": ("lat", "latitude", "широта"),
    "lon": ("lon", "longitude", "lng", "long", "долгота"),
    "dest": ("dest", "wb_dest", "dest_id"),
    "active": ("is_active", "active", "enabled"),
}
SKU_COLUMNS = {
    "sku": ("sku", "nm", "nm_id", "nmid", "article", "артикул"),
    "marketplace": ("marketplace", "mp", "platform", "площадка"),
    "active": ("is_active", "active", "enabled"),
}

RESULT_COLUMNS = (
    ("collected_at", "TIMESTAMP"),
    ("city", "TEXT"),
    ("city_name", "TEXT"),
    ("dest", "BIGINT"),
    ("sku", "TEXT"),
    ("name", "TEXT"),
    ("brand", "TEXT"),
    ("price", "NUMERIC"),
    ("price_base", "NUMERIC"),
    ("price_total", "NUMERIC"),
    ("price_wallet_est", "NUMERIC"),
    ("currency", "TEXT"),
    ("qty", "INTEGER"),
    ("wh_count", "INTEGER"),
    ("wh_main", "BIGINT"),
    ("wh_main_qty", "INTEGER"),
    ("delivery_h", "INTEGER"),
    ("is_available", "BOOLEAN"),
    ("supplier", "TEXT"),
    ("rating", "NUMERIC"),
)

_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def _check_table_name(name: str) -> str:
    """Имя таблицы подставляется в SQL текстом, поэтому проверяем его строго."""
    if not _SAFE_NAME.match(name or ""):
        raise DbError(
            f"недопустимое имя таблицы: {name!r} "
            "(ожидаю schema.table или table из букв, цифр и подчёркиваний)"
        )
    return name


# ──────────────────────────────────────────────────────────────
# подключение
# ──────────────────────────────────────────────────────────────

class Db:
    """Тонкая обёртка: прячет разницу между psycopg и sqlite3."""

    def __init__(self, conn: Any, kind: str) -> None:
        self.conn = conn
        self.kind = kind          # "postgres" | "sqlite"
        self.ph = "%s" if kind == "postgres" else "?"

    def query(self, sql: str, params: Sequence[Any] = ()) -> tuple[list[str], list[tuple]]:
        cur = self.conn.cursor()
        try:
            cur.execute(sql, tuple(params))
            columns = [d[0].lower() for d in (cur.description or [])]
            return columns, cur.fetchall()
        finally:
            cur.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        cur = self.conn.cursor()
        try:
            cur.execute(sql, tuple(params))
        finally:
            cur.close()

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        cur = self.conn.cursor()
        try:
            cur.executemany(sql, [tuple(r) for r in rows])
        finally:
            cur.close()

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


def _dsn_from_env() -> str | None:
    host = os.getenv("RPM_PG_HOST") or os.getenv("PGHOST")
    if not host:
        return None
    port = os.getenv("RPM_PG_PORT") or os.getenv("PGPORT") or "5432"
    db = os.getenv("RPM_PG_DB") or os.getenv("PGDATABASE") or "postgres"
    user = os.getenv("RPM_PG_USER") or os.getenv("PGUSER") or "postgres"
    password = os.getenv("RPM_PG_PASSWORD") or os.getenv("PGPASSWORD") or ""
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def connect(dsn: str | None = None) -> Db:
    """Подключиться по строке или по переменным окружения."""
    dsn = (dsn or os.getenv("RPM_DB_URL") or _dsn_from_env() or "").strip()
    if not dsn:
        raise DbError(
            "не задано подключение к БД: передай --db-url или задай PGHOST/PGDATABASE/PGUSER/PGPASSWORD"
        )

    if dsn.startswith("sqlite:"):
        import sqlite3

        path = dsn.split("://", 1)[1] if "://" in dsn else dsn.split(":", 1)[1]
        path = path.lstrip("/") if path.startswith("///") else path
        conn = sqlite3.connect(path or ":memory:")
        return Db(conn, "sqlite")

    scheme = urlsplit(dsn).scheme
    if scheme not in ("postgres", "postgresql"):
        raise DbError(f"поддерживаются postgresql:// и sqlite:, а не {scheme!r}")

    try:
        import psycopg  # psycopg 3
        return Db(psycopg.connect(dsn), "postgres")
    except ImportError:
        pass
    try:
        import psycopg2
        return Db(psycopg2.connect(dsn), "postgres")
    except ImportError as exc:
        raise DbError("нужен драйвер PostgreSQL: pip install psycopg2-binary") from exc


# ──────────────────────────────────────────────────────────────
# чтение
# ──────────────────────────────────────────────────────────────

def _pick(columns: Sequence[str], variants: Sequence[str]) -> str | None:
    lowered = {c.lower(): c for c in columns}
    for variant in variants:
        if variant in lowered:
            return lowered[variant]
    return None


def load_cities(db: Db, table: str) -> dict[str, dict[str, Any]]:
    """Прочитать города. Возвращает тот же формат, что и cities.json."""
    table = _check_table_name(table)
    columns, rows = db.query(f"SELECT * FROM {table}")  # noqa: S608 — имя проверено выше
    if not rows:
        raise DbError(f"таблица городов {table} пуста")

    col = {key: _pick(columns, variants) for key, variants in CITY_COLUMNS.items()}
    missing = [key for key in ("code", "lat", "lon") if not col[key] and key != "lat" and key != "lon"]
    if not col["code"]:
        raise DbError(
            f"в таблице {table} нет колонки с кодом города. "
            f"Ожидаю одну из: {', '.join(CITY_COLUMNS['code'])}. Есть: {', '.join(columns)}"
        )
    if not col["dest"] and not (col["lat"] and col["lon"]):
        raise DbError(
            f"в таблице {table} нужны либо колонка dest, либо пара координат "
            f"({'/'.join(CITY_COLUMNS['lat'])} и {'/'.join(CITY_COLUMNS['lon'])}). "
            f"Есть: {', '.join(columns)}"
        )

    index = {name: position for position, name in enumerate(columns)}
    cities: dict[str, dict[str, Any]] = {}
    for row in rows:
        def value(key: str) -> Any:
            column = col.get(key)
            return row[index[column.lower()]] if column else None

        if col["active"] is not None:
            flag = value("active")
            if flag in (0, False, "0", "false", "no", "n"):
                continue

        code = str(value("code") or "").strip()
        if not code:
            continue
        entry: dict[str, Any] = {
            "name": str(value("name") or code),
            "address": str(value("name") or code),
        }
        lat, lon = value("lat"), value("lon")
        if lat is not None and lon is not None:
            entry["lat"], entry["lon"] = float(lat), float(lon)
        dest = value("dest")
        if dest is not None and str(dest).strip() != "":
            entry["dest"] = int(dest)
        cities[code] = entry

    if not cities:
        raise DbError(f"в таблице {table} нет активных городов")
    return cities


def load_skus(db: Db, table: str, marketplace: str = "wb") -> list[str]:
    """Прочитать артикулы. Если есть колонка marketplace — фильтруем по ней."""
    table = _check_table_name(table)
    columns, rows = db.query(f"SELECT * FROM {table}")  # noqa: S608 — имя проверено выше
    if not rows:
        raise DbError(f"таблица товаров {table} пуста")

    col = {key: _pick(columns, variants) for key, variants in SKU_COLUMNS.items()}
    if not col["sku"]:
        raise DbError(
            f"в таблице {table} нет колонки с артикулом. "
            f"Ожидаю одну из: {', '.join(SKU_COLUMNS['sku'])}. Есть: {', '.join(columns)}"
        )

    index = {name: position for position, name in enumerate(columns)}
    skus: list[str] = []
    for row in rows:
        def value(key: str) -> Any:
            column = col.get(key)
            return row[index[column.lower()]] if column else None

        if col["active"] is not None:
            flag = value("active")
            if flag in (0, False, "0", "false", "no", "n"):
                continue
        if col["marketplace"] is not None:
            mp = str(value("marketplace") or "").strip().lower()
            if mp and mp != marketplace:
                continue

        sku = str(value("sku") or "").strip()
        if sku.isdigit():
            skus.append(sku)

    if not skus:
        raise DbError(f"в таблице {table} нет артикулов для площадки {marketplace!r}")
    return list(dict.fromkeys(skus))


# ──────────────────────────────────────────────────────────────
# запись
# ──────────────────────────────────────────────────────────────

def ensure_results_table(db: Db, table: str) -> None:
    table = _check_table_name(table)
    if db.kind == "postgres":
        body = ", ".join(f"{name} {sql_type}" for name, sql_type in RESULT_COLUMNS)
        db.execute(f"CREATE TABLE IF NOT EXISTS {table} (id BIGSERIAL PRIMARY KEY, {body})")
    else:
        mapping = {"NUMERIC": "REAL", "BIGINT": "INTEGER", "BOOLEAN": "INTEGER", "TIMESTAMP": "TEXT"}
        body = ", ".join(f"{name} {mapping.get(sql_type, sql_type)}" for name, sql_type in RESULT_COLUMNS)
        db.execute(f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY AUTOINCREMENT, {body})")
    db.commit()


def save_results(db: Db, table: str, rows: Sequence[dict[str, Any]]) -> int:
    """Записать собранные строки. Таблица создаётся, если её нет."""
    if not rows:
        return 0
    table = _check_table_name(table)
    ensure_results_table(db, table)

    names = [name for name, _ in RESULT_COLUMNS]
    placeholders = ", ".join([db.ph] * len(names))
    sql = f"INSERT INTO {table} ({', '.join(names)}) VALUES ({placeholders})"  # noqa: S608

    payload = []
    for row in rows:
        values = []
        for name in names:
            value = row.get(name)
            if name == "is_available" and db.kind == "sqlite":
                value = 1 if value else 0
            values.append(value)
        payload.append(values)

    db.executemany(sql, payload)
    db.commit()
    return len(payload)
