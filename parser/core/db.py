# -*- coding: utf-8 -*-
"""PostgreSQL: источники входных данных и приёмник результатов. Авто-создаёт таблицы.
Проверено против PostgreSQL 16."""
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from input_models import CityRecord, normalize_city_record, normalize_product_rows

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None


class ParserDB:
    def __init__(self, host="localhost", port=5432, dbname="parser", user="postgres", password=""):
        if psycopg2 is None:
            raise ImportError("Установите psycopg2: pip install psycopg2-binary")
        self.dsn = f"host={host} port={port} dbname={dbname} user={user} password={password}"
        self._test_conn()
        self._ensure_tables()

    @classmethod
    def from_params(cls, params):
        return cls(**params)

    @contextmanager
    def _connect(self):
        conn = psycopg2.connect(self.dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _test_conn(self):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")

    def _ensure_tables(self):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS parser_skus (
                        id SERIAL PRIMARY KEY,
                        sku VARCHAR(50) NOT NULL,
                        marketplace VARCHAR(20) NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(sku, marketplace)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS parser_cities (
                        city VARCHAR(255) PRIMARY KEY,
                        proxy TEXT NOT NULL,
                        proxy_user TEXT NOT NULL,
                        proxy_password TEXT NOT NULL,
                        wb_dest VARCHAR(255)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS parser_results (
                        id SERIAL PRIMARY KEY,
                        run_id VARCHAR(50),
                        sku VARCHAR(50),
                        marketplace VARCHAR(20),
                        region_code VARCHAR(20),
                        price NUMERIC(12,2),
                        price_base NUMERIC(12,2),
                        price_card NUMERIC(12,2),
                        price_regular NUMERIC(12,2),
                        price_original NUMERIC(12,2),
                        currency VARCHAR(10),
                        is_available BOOLEAN,
                        source VARCHAR(50),
                        parsed_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                # мягкая миграция старой схемы (если таблица уже была без новых колонок)
                for col in ("price_card", "price_regular", "price_original"):
                    cur.execute(f"ALTER TABLE parser_results ADD COLUMN IF NOT EXISTS {col} NUMERIC(12,2)")

    # ── SKU ──
    def load_skus(self, active_only=True):
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                sql = "SELECT sku, marketplace FROM parser_skus"
                if active_only:
                    sql += " WHERE is_active = TRUE"
                sql += " ORDER BY id"
                cur.execute(sql)
                return normalize_product_rows(cur.fetchall(), source="parser_skus")

    def add_sku(self, sku, marketplace):
        product = normalize_product_rows(
            [{"sku": sku, "marketplace": marketplace}], source="parser_skus insert"
        )
        normalized_marketplace = "wb" if product["wb"] else "ozon"
        normalized_sku = product[normalized_marketplace][0]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO parser_skus (sku, marketplace) VALUES (%s, %s)
                               ON CONFLICT (sku, marketplace) DO NOTHING""",
                            (normalized_sku, normalized_marketplace))

    # ── Города ──
    def load_cities(self):
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT city, proxy, proxy_user, proxy_password, wb_dest
                    FROM parser_cities
                    ORDER BY city
                """)
                return [
                    normalize_city_record(row, context=f"parser_cities row {index}")
                    for index, row in enumerate(cur.fetchall(), start=1)
                ]

    def add_city(self, city):
        record = normalize_city_record(city, context="parser_cities insert")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO parser_cities (city, proxy, proxy_user, proxy_password, wb_dest)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (city) DO UPDATE SET
                        proxy = EXCLUDED.proxy,
                        proxy_user = EXCLUDED.proxy_user,
                        proxy_password = EXCLUDED.proxy_password,
                        wb_dest = EXCLUDED.wb_dest
                """, (
                    record.city,
                    record.proxy,
                    record.proxy_user,
                    record.proxy_password,
                    record.wb_dest,
                ))
        return CityRecord(**record.as_dict())

    # ── Результаты ──
    def save_results(self, results, run_id=None):
        if not results:
            return None
        if run_id is None:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + str(uuid.uuid4())[:8]
        with self._connect() as conn:
            with conn.cursor() as cur:
                for r in results:
                    cur.execute("""
                        INSERT INTO parser_results
                        (run_id, sku, marketplace, region_code, price, price_base,
                         price_card, price_regular, price_original, currency, is_available, source)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        run_id, r.get("sku"), r.get("marketplace", "unknown"), r.get("region_code"),
                        r.get("price"), r.get("price_base"),
                        r.get("price_card"), r.get("price_regular"), r.get("price_original"),
                        r.get("currency", "RUB"), r.get("is_available", True), r.get("source", "unknown"),
                    ))
        return run_id

    def list_results(self, run_id=None, limit=100):
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if run_id:
                    cur.execute("SELECT * FROM parser_results WHERE run_id=%s ORDER BY parsed_at DESC LIMIT %s",
                                (run_id, limit))
                else:
                    cur.execute("SELECT * FROM parser_results ORDER BY parsed_at DESC LIMIT %s", (limit,))
                return cur.fetchall()


def wizard_connect():
    """Интерактивный ввод параметров PG (десктоп)."""
    print("\n   🐘 Подключение к PostgreSQL")
    host = input("   Хост (localhost): ").strip() or "localhost"
    port = input("   Порт (5432): ").strip() or "5432"
    dbname = input("   База (parser): ").strip() or "parser"
    user = input("   Пользователь (postgres): ").strip() or "postgres"
    password = input("   Пароль: ").strip()
    return {"host": host, "port": int(port), "dbname": dbname, "user": user, "password": password}
