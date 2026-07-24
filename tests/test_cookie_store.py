"""Unit tests for FsCookieStore and is_stale — no network, always runs in CI."""

import datetime
import json
import os

from app.cookies.base import CookieBundle, is_stale
from app.cookies.fs import FsCookieStore
from app.enums import Marketplace


def _bundle(*, warmed_at: datetime.datetime, stale: bool = False) -> CookieBundle:
    return CookieBundle(
        marketplace=Marketplace.OZON,
        region_code="msk",
        storage_state={"cookies": [{"name": "sid", "value": "abc"}]},
        warmed_at=warmed_at,
        stale=stale,
        source_ref="direct",
    )


def test_save_load_round_trip(tmp_path) -> None:
    store = FsCookieStore(str(tmp_path))
    bundle = _bundle(warmed_at=datetime.datetime.now(datetime.UTC))

    store.save(bundle)
    loaded = store.load(Marketplace.OZON, "msk")

    assert loaded == bundle


def test_load_missing_returns_none(tmp_path) -> None:
    store = FsCookieStore(str(tmp_path))

    assert store.load(Marketplace.OZON, "spb") is None


def test_mark_stale_flips_flag(tmp_path) -> None:
    store = FsCookieStore(str(tmp_path))
    store.save(_bundle(warmed_at=datetime.datetime.now(datetime.UTC)))

    store.mark_stale(Marketplace.OZON, "msk")

    assert store.load(Marketplace.OZON, "msk").stale is True


def test_mark_stale_missing_bundle_is_a_no_op(tmp_path) -> None:
    store = FsCookieStore(str(tmp_path))

    store.mark_stale(Marketplace.OZON, "spb")

    assert store.load(Marketplace.OZON, "spb") is None


def test_is_stale_false_when_fresh() -> None:
    bundle = _bundle(warmed_at=datetime.datetime.now(datetime.UTC))

    assert is_stale(bundle, ttl_hours=12) is False


def test_is_stale_true_by_ttl_expiry() -> None:
    bundle = _bundle(warmed_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=13))

    assert is_stale(bundle, ttl_hours=12) is True


def test_is_stale_true_by_explicit_flag() -> None:
    bundle = _bundle(warmed_at=datetime.datetime.now(datetime.UTC), stale=True)

    assert is_stale(bundle, ttl_hours=12) is True


def test_load_bundle_without_address_label_defaults_to_none(tmp_path) -> None:
    store = FsCookieStore(str(tmp_path))
    path = os.path.join(str(tmp_path), "ozon", "msk.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "marketplace": "ozon",
        "region_code": "msk",
        "storage_state": {"cookies": []},
        "warmed_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "stale": False,
        "source_ref": "direct",
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)

    loaded = store.load(Marketplace.OZON, "msk")

    assert loaded is not None
    assert loaded.address_label is None
