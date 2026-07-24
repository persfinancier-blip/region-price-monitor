"""`cookies` script — one-button collect + health + manual control (ADR-0008, ADR-0012).

Thin wrapper over `app.cookies.warm.warm_all` and `FsCookieStore`: `collect(marketplace)`
walks the local cities store's effective cities (Ozon per-city, WB single session);
`status()` reports stored bundles with health (valid / expiring / stale via `is_stale`);
`set_manual`/`clear` let the operator paste/edit/drop a cookie by hand. No business logic
in the panel routes — they call straight through here.
"""

import argparse
import asyncio
import datetime
import json
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.cookies.base import CookieBundle, CookieStore, is_stale
from app.cookies.fs import make_cookie_store
from app.cookies.warm import CancelToken, ProgressReporter, WalkCity, warm_all
from app.enums import Marketplace
from app.scripts import cities as cities_store


@dataclass(frozen=True)
class CookieHealth:
    """Health verdict for one stored (marketplace, region_code) bundle."""

    marketplace: str
    region_code: str
    warmed_at: datetime.datetime | None
    age_hours: float | None
    status: str  # "valid" | "expiring" | "stale" | "missing"


_EXPIRING_FRACTION = 0.25


def _health_status(bundle: CookieBundle | None, ttl_hours: int) -> str:
    if bundle is None:
        return "missing"
    if is_stale(bundle, ttl_hours):
        return "stale"
    age = datetime.datetime.now(datetime.UTC) - bundle.warmed_at
    remaining_hours = ttl_hours - age.total_seconds() / 3600
    if remaining_hours <= ttl_hours * _EXPIRING_FRACTION:
        return "expiring"
    return "valid"


def _walk_cities(effective: list[cities_store.EffectiveCity], marketplace: Marketplace) -> list[WalkCity]:
    mp_key = marketplace.value
    walk = []
    for city in effective:
        eff_mp = city.marketplaces.get(mp_key)
        if eff_mp is None:
            continue
        walk.append(WalkCity(code=city.code, name=city.name, geo=city.geo, proxy_url=eff_mp.proxy))
    return walk


async def collect(
    marketplace: Marketplace,
    *,
    settings: Settings | None = None,
    store: CookieStore | None = None,
    cancel: CancelToken | None = None,
    on_progress: ProgressReporter | None = None,
) -> list[str]:
    """Run `warm_all` over the cities store's effective cities for `marketplace`.

    Returns the list of city codes (or `_session` for WB) the walk reported on, in order.
    """
    settings = settings or get_settings()
    store = store or make_cookie_store(settings)

    config = await cities_store.load(settings)
    effective = cities_store.list_effective(config)
    walk_cities = _walk_cities(effective, marketplace)

    results = await asyncio.to_thread(
        warm_all, store, marketplace, walk_cities, cancel=cancel, on_progress=on_progress
    )
    return [r.city_code for r in results]


async def status(
    marketplace: Marketplace | None = None,
    *,
    settings: Settings | None = None,
    store: CookieStore | None = None,
) -> list[CookieHealth]:
    """List stored bundles with health for one marketplace, or both if omitted."""
    settings = settings or get_settings()
    store = store or make_cookie_store(settings)

    config = await cities_store.load(settings)
    codes: list[str] = [c.code for c in config.cities]
    codes.append("_session")

    marketplaces = [marketplace] if marketplace is not None else list(Marketplace)
    reports = []
    seen: set[tuple[str, str]] = set()
    for mp in marketplaces:
        for code in codes:
            key = (mp.value, code)
            if key in seen:
                continue
            seen.add(key)
            bundle = store.load(mp, code)
            if bundle is None:
                continue
            age_hours = (datetime.datetime.now(datetime.UTC) - bundle.warmed_at).total_seconds() / 3600
            reports.append(
                CookieHealth(
                    marketplace=mp.value,
                    region_code=code,
                    warmed_at=bundle.warmed_at,
                    age_hours=age_hours,
                    status=_health_status(bundle, settings.ozon_cookie_ttl_hours),
                )
            )
    return reports


def set_manual(
    marketplace: Marketplace,
    region_code: str,
    raw_storage_state: dict[str, object],
    *,
    settings: Settings | None = None,
    store: CookieStore | None = None,
) -> None:
    """Paste/edit a cookie bundle by hand — same shape `warm_all` would have saved."""
    settings = settings or get_settings()
    store = store or make_cookie_store(settings)
    store.save(
        CookieBundle(
            marketplace=marketplace,
            region_code=region_code,
            storage_state=raw_storage_state,
            warmed_at=datetime.datetime.now(datetime.UTC),
            stale=False,
            source_ref="manual",
        )
    )


def clear(
    marketplace: Marketplace,
    region_code: str,
    *,
    settings: Settings | None = None,
    store: CookieStore | None = None,
) -> None:
    """Drop one stored bundle by marking it stale (no delete verb on `CookieStore`)."""
    settings = settings or get_settings()
    store = store or make_cookie_store(settings)
    store.mark_stale(marketplace, region_code)


def format_status(reports: list[CookieHealth]) -> str:
    """Render the health report as human-readable text."""
    if not reports:
        return "no cookies stored"
    lines = []
    for r in reports:
        age = f"{r.age_hours:.1f}h" if r.age_hours is not None else "—"
        lines.append(f"  {r.marketplace}/{r.region_code}: status={r.status} age={age}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint: `collect`/`status`/`set-manual`/`clear`, mirroring the CLI verb."""
    parser = argparse.ArgumentParser(prog="app.scripts.cookies", description="Manage cookie bundles")
    subparsers = parser.add_subparsers(dest="action", required=True)

    collect_parser = subparsers.add_parser("collect", help="Login-once + auto city-walk collect")
    collect_parser.add_argument("marketplace", choices=["wb", "ozon"])

    status_parser = subparsers.add_parser("status", help="Print health for stored bundles")
    status_parser.add_argument("marketplace", nargs="?", choices=["wb", "ozon"], default=None)

    set_parser = subparsers.add_parser("set-manual", help="Paste a cookie bundle from a JSON file")
    set_parser.add_argument("marketplace", choices=["wb", "ozon"])
    set_parser.add_argument("region_code")
    set_parser.add_argument("file", help="Path to a JSON file holding the storage_state")

    clear_parser = subparsers.add_parser("clear", help="Mark a stored bundle stale")
    clear_parser.add_argument("marketplace", choices=["wb", "ozon"])
    clear_parser.add_argument("region_code")

    args = parser.parse_args(argv)

    if args.action == "collect":
        codes = asyncio.run(collect(Marketplace(args.marketplace)))
        print(f"collected: {', '.join(codes) or '(none)'}")
        return 0
    if args.action == "status":
        mp = Marketplace(args.marketplace) if args.marketplace else None
        print(format_status(asyncio.run(status(mp))))
        return 0
    if args.action == "set-manual":
        with open(args.file, encoding="utf-8") as fh:
            raw_storage_state = json.load(fh)
        set_manual(Marketplace(args.marketplace), args.region_code, raw_storage_state)
        print(f"set: {args.marketplace}/{args.region_code}")
        return 0
    if args.action == "clear":
        clear(Marketplace(args.marketplace), args.region_code)
        print(f"cleared: {args.marketplace}/{args.region_code}")
        return 0

    parser.error(f"unknown action: {args.action}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
