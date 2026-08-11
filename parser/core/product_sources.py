from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from input_models import InputValidationError, normalize_product_mapping, normalize_product_rows


def _read_tabular_rows(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        raise InputValidationError(f"product file not found: {source}")
    suffix = source.suffix.lower()
    if suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if suffix in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise InputValidationError("Excel product input requires pandas/openpyxl") from exc
        return pd.read_excel(source).to_dict("records")
    raise InputValidationError(f"unsupported product file format: {suffix or '<none>'}")


def load_products_file(path: str | Path) -> dict[str, list[str]]:
    return normalize_product_rows(_read_tabular_rows(path), source=f"product file {Path(path)}")


def load_products_json(path: str | Path) -> dict[str, list[str]]:
    source = Path(path)
    if not source.exists():
        raise InputValidationError(f"products JSON not found: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputValidationError(f"cannot read products JSON {source}: {exc}") from exc
    return normalize_product_mapping(raw, source=f"products JSON {source}")
