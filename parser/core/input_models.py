from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping

SUPPORTED_MARKETPLACES = ("wb", "ozon")


class InputValidationError(ValueError):
    """Raised when user-supplied product/city data violates the canonical input contract."""


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "<na>"}


def _required_text(value: Any, field: str, *, context: str) -> str:
    if _is_blank(value):
        raise InputValidationError(f"{context}: required field '{field}' is missing or blank")
    return str(value).strip()


def normalize_sku(value: Any, *, context: str = "product") -> str:
    if _is_blank(value):
        raise InputValidationError(f"{context}: required field 'sku' is missing or blank")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize_product_rows(rows: Iterable[Mapping[str, Any]], *, source: str = "product input") -> dict[str, list[str]]:
    products = {"wb": [], "ozon": []}
    seen_any = False
    for index, raw in enumerate(rows, start=1):
        seen_any = True
        if not isinstance(raw, Mapping):
            raise InputValidationError(f"{source} row {index}: expected a mapping")
        row = {str(key).strip().lower(): value for key, value in raw.items()}
        context = f"{source} row {index}"
        marketplace = _required_text(row.get("marketplace"), "marketplace", context=context).lower()
        if marketplace not in products:
            raise InputValidationError(
                f"{context}: unsupported marketplace '{marketplace}', expected one of {SUPPORTED_MARKETPLACES}"
            )
        sku = normalize_sku(row.get("sku"), context=context)
        products[marketplace].append(sku)
    if not seen_any:
        raise InputValidationError(f"{source}: no product rows found")
    return products


def normalize_product_mapping(raw: Mapping[str, Iterable[Any]], *, source: str = "product mapping") -> dict[str, list[str]]:
    if not isinstance(raw, Mapping):
        raise InputValidationError(f"{source}: expected mapping with wb/ozon keys")
    products = {"wb": [], "ozon": []}
    for key, values in raw.items():
        marketplace = str(key).strip().lower()
        if marketplace not in products:
            if values:
                raise InputValidationError(f"{source}: unsupported marketplace '{marketplace}'")
            continue
        if values is None:
            continue
        if isinstance(values, (str, bytes)):
            values = [values]
        for index, value in enumerate(values, start=1):
            products[marketplace].append(normalize_sku(value, context=f"{source} {marketplace}[{index}]"))
    return products


@dataclass(frozen=True, repr=False)
class CityRecord:
    city: str
    proxy: str
    proxy_user: str
    proxy_password: str
    wb_dest: str | None = None

    def __repr__(self) -> str:
        return (
            "CityRecord("
            f"city={self.city!r}, proxy={self.proxy!r}, proxy_user='***', "
            "proxy_password='***', "
            f"wb_dest={self.wb_dest!r})"
        )

    def as_dict(self, *, include_secret: bool = True) -> dict[str, str | None]:
        result: dict[str, str | None] = {
            "city": self.city,
            "proxy": self.proxy,
            "proxy_user": self.proxy_user if include_secret else "***",
            "proxy_password": self.proxy_password if include_secret else "***",
            "wb_dest": self.wb_dest,
        }
        return result


def normalize_city_record(raw: Mapping[str, Any] | CityRecord, *, context: str = "city input") -> CityRecord:
    if isinstance(raw, CityRecord):
        return raw
    if not isinstance(raw, Mapping):
        raise InputValidationError(f"{context}: expected a mapping")
    row = {str(key).strip().lower(): value for key, value in raw.items()}
    city = _required_text(row.get("city"), "city", context=context)
    proxy = _required_text(row.get("proxy"), "proxy", context=context)
    proxy_user = _required_text(row.get("proxy_user"), "proxy_user", context=context)
    proxy_password = _required_text(row.get("proxy_password"), "proxy_password", context=context)
    wb_dest_raw = row.get("wb_dest")
    if _is_blank(wb_dest_raw):
        wb_dest = None
    elif isinstance(wb_dest_raw, int) and not isinstance(wb_dest_raw, bool):
        wb_dest = str(wb_dest_raw)
    elif isinstance(wb_dest_raw, float) and wb_dest_raw.is_integer():
        wb_dest = str(int(wb_dest_raw))
    else:
        wb_dest = str(wb_dest_raw).strip()
    return CityRecord(
        city=city,
        proxy=proxy,
        proxy_user=proxy_user,
        proxy_password=proxy_password,
        wb_dest=wb_dest,
    )


def normalize_city_rows(rows: Iterable[Mapping[str, Any] | CityRecord], *, source: str = "city input") -> list[CityRecord]:
    cities: list[CityRecord] = []
    for index, row in enumerate(rows, start=1):
        cities.append(normalize_city_record(row, context=f"{source} row {index}"))
    if not cities:
        raise InputValidationError(f"{source}: no city rows found")
    return cities
