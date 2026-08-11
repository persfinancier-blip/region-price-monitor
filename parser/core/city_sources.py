from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from input_models import CityRecord, InputValidationError, normalize_city_rows


def _read_tabular_rows(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        raise InputValidationError(f"city file not found: {source}")
    suffix = source.suffix.lower()
    if suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if suffix in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise InputValidationError("Excel city input requires pandas/openpyxl") from exc
        return pd.read_excel(source).to_dict("records")
    raise InputValidationError(f"unsupported city file format: {suffix or '<none>'}")


def load_cities_file(path: str | Path) -> list[CityRecord]:
    return normalize_city_rows(_read_tabular_rows(path), source=f"city file {Path(path)}")
