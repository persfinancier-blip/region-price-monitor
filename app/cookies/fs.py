"""FsCookieStore — one JSON file per (marketplace × region_code) under a gitignored dir."""

import datetime
import json
import logging
import os
from typing import TYPE_CHECKING, Any

from app.cookies.base import CookieBundle
from app.enums import Marketplace

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)


class FsCookieStore:
    """Filesystem-backed CookieStore — never logs cookie contents (ADR-0005 constraint)."""

    def __init__(self, base_dir: str) -> None:
        self._base_dir = base_dir

    def _path(self, marketplace: Marketplace, region_code: str) -> str:
        return os.path.join(self._base_dir, marketplace.value, f"{region_code}.json")

    def load(self, marketplace: Marketplace, region_code: str) -> CookieBundle | None:
        path = self._path(marketplace, region_code)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        return CookieBundle(
            marketplace=Marketplace(data["marketplace"]),
            region_code=data["region_code"],
            storage_state=data["storage_state"],
            warmed_at=datetime.datetime.fromisoformat(data["warmed_at"]),
            stale=data.get("stale", False),
            source_ref=data.get("source_ref"),
        )

    def save(self, bundle: CookieBundle) -> None:
        path = self._path(bundle.marketplace, bundle.region_code)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "marketplace": bundle.marketplace.value,
            "region_code": bundle.region_code,
            "storage_state": bundle.storage_state,
            "warmed_at": bundle.warmed_at.isoformat(),
            "stale": bundle.stale,
            "source_ref": bundle.source_ref,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        logger.info(
            "cookie bundle saved: marketplace=%s region=%s source_ref=%s",
            bundle.marketplace.value,
            bundle.region_code,
            bundle.source_ref,
        )

    def mark_stale(self, marketplace: Marketplace, region_code: str) -> None:
        bundle = self.load(marketplace, region_code)
        if bundle is None:
            return
        self.save(
            CookieBundle(
                marketplace=bundle.marketplace,
                region_code=bundle.region_code,
                storage_state=bundle.storage_state,
                warmed_at=bundle.warmed_at,
                stale=True,
                source_ref=bundle.source_ref,
            )
        )


def make_cookie_store(settings: "Settings") -> FsCookieStore:
    """Factory: only a filesystem store this phase (DB-backed store is Фаза 8)."""
    return FsCookieStore(settings.cookie_store_dir)
