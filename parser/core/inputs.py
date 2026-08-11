from __future__ import annotations

from pathlib import Path
from typing import Any

from city_sources import load_cities_file
from input_models import InputValidationError, normalize_city_rows, normalize_product_mapping
from product_sources import load_products_file, load_products_json


class InputSourceError(InputValidationError):
    pass


def _require_db(db: Any, source_name: str) -> Any:
    if db is None:
        raise InputSourceError(f"{source_name} source requires ParserDB")
    return db


def load_input_bundle(
    *,
    product_source: str,
    city_source: str,
    product_file: str | Path | None = None,
    city_file: str | Path | None = None,
    products_json: str | Path | None = None,
    db: Any = None,
) -> dict[str, Any]:
    product_source = str(product_source).strip().lower()
    city_source = str(city_source).strip().lower()

    if product_source == "file":
        if product_file is None:
            raise InputSourceError("product file source requires product_file")
        products = load_products_file(product_file)
    elif product_source in {"db", "postgres", "postgresql"}:
        products = normalize_product_mapping(_require_db(db, "product DB").load_skus(active_only=True), source="product DB")
    elif product_source == "json":
        if products_json is None:
            raise InputSourceError("product JSON source requires products_json")
        products = load_products_json(products_json)
    else:
        raise InputSourceError(f"unsupported product source '{product_source}'")

    if city_source == "file":
        if city_file is None:
            raise InputSourceError("city file source requires city_file")
        cities = load_cities_file(city_file)
    elif city_source in {"db", "postgres", "postgresql"}:
        cities = normalize_city_rows(_require_db(db, "city DB").load_cities(), source="city DB")
    else:
        raise InputSourceError(f"unsupported city source '{city_source}'")

    if not (products["wb"] or products["ozon"]):
        raise InputSourceError("product source produced an empty ProductSet")
    if not cities:
        raise InputSourceError("city source produced an empty CitySet")

    return {"products": products, "cities": cities}
