# -*- coding: utf-8 -*-
"""Единая конфигурация. Пути привязаны к папке проекта (не к cwd).
PG-подключение — из окружения (сервер) или из config.json (десктоп)."""
import os
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROFILES_DIR = Path(os.getenv("RPM_PROFILES", BASE / "profiles"))
RESULTS_DIR = Path(os.getenv("RPM_RESULTS", BASE / "results"))
DEBUG_DIR = Path(os.getenv("RPM_DEBUG", BASE / "debug"))
CONFIG_PATH = Path(os.getenv("RPM_CONFIG", BASE / "config.json"))
PRODUCTS_PATH = Path(os.getenv("RPM_PRODUCTS", BASE / "products.json"))

for _d in (PROFILES_DIR, RESULTS_DIR, DEBUG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Ozon: TLS-impersonate. edge — единственная рабочая стратегия (проверено).
OZON_STRATEGIES = [("edge", True), ("edge", False)]

WB_API_URL = "https://card.wb.ru/cards/v4/detail"
WB_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://www.wildberries.ru/",
    "Accept": "application/json",
}


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {"regions": []}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def load_products():
    if PRODUCTS_PATH.exists():
        return json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    return {"wb": [], "ozon": []}


def pg_params_from_env():
    """PG-параметры из окружения (для сервера). None, если не заданы."""
    host = os.getenv("RPM_PG_HOST") or os.getenv("PGHOST")
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.getenv("RPM_PG_PORT", os.getenv("PGPORT", "5432"))),
        "dbname": os.getenv("RPM_PG_DB", os.getenv("PGDATABASE", "parser")),
        "user": os.getenv("RPM_PG_USER", os.getenv("PGUSER", "postgres")),
        "password": os.getenv("RPM_PG_PASSWORD", os.getenv("PGPASSWORD", "")),
    }
