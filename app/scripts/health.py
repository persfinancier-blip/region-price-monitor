"""`health` script — proxy health + cookie staleness, optional warming (ADR-0008).

Wraps `ProxyHealthService` (proxy cooldown, `app/proxy/health.py`) and
`app.cookies.base.is_stale` (cookie freshness) into a single report. When
`fix=True`, stale Ozon cookies are re-warmed via `warm_if_stale`. Standalone,
prints a report and exits non-zero when unhealthy and not fixed; `--fix`
triggers warming.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field

from app.config import Settings, get_settings
from app.cookies.base import CookieStore, is_stale
from app.cookies.fs import make_cookie_store
from app.cookies.warm import CookieWarmer, warm_if_stale
from app.enums import Marketplace
from app.models import Region
from app.proxy.base import ProxyProvider
from app.proxy.health import ProxyHealthService
from app.proxy.static import make_proxy_provider
from app.scheduler.runner import SessionFactory
from app.storage.factory import make_storage


@dataclass(frozen=True)
class RegionHealth:
    """Health verdict for one region's Ozon cookie + its proxy_ref cooldown."""

    region_code: str
    proxy_ref: str | None
    cooling_down: bool
    cookie_stale: bool
    warmed: bool = False


@dataclass(frozen=True)
class HealthReport:
    """Aggregated health verdict across active regions."""

    regions: list[RegionHealth] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        """True when no region is cooling down or has a stale/missing cookie."""
        return all(not r.cooling_down and not r.cookie_stale for r in self.regions)


async def _region_health(
    region: Region,
    *,
    proxy_ref: str | None,
    health_service: ProxyHealthService,
    cookie_store: CookieStore,
    settings: Settings,
    fix: bool,
    warmer: CookieWarmer,
) -> RegionHealth:
    cooling_down = False
    if proxy_ref is not None:
        verdict = await health_service.verdict(region.code, proxy_ref)
        cooling_down = verdict.cooling_down

    bundle = cookie_store.load(Marketplace.OZON, region.code)
    stale = bundle is None or is_stale(bundle, settings.ozon_cookie_ttl_hours)

    warmed = False
    if stale and fix and "ozon" in region.geo:
        warm_if_stale(cookie_store, warmer, Marketplace.OZON, region, settings.ozon_cookie_ttl_hours, None)
        stale = False
        warmed = True

    return RegionHealth(
        region_code=region.code,
        proxy_ref=proxy_ref,
        cooling_down=cooling_down,
        cookie_stale=stale,
        warmed=warmed,
    )


async def run(
    fix: bool = False,
    *,
    session_factory: SessionFactory | None = None,
    settings: Settings | None = None,
    cookie_store: CookieStore | None = None,
    warmer: CookieWarmer | None = None,
) -> HealthReport:
    """Check proxy cooldown + Ozon cookie staleness for active regions; warm stale cookies if `fix`."""
    settings = settings or get_settings()
    session_factory = session_factory or make_storage(settings)
    cookie_store = cookie_store or make_cookie_store(settings)
    warmer = warmer or CookieWarmer()
    health_service = ProxyHealthService(session_factory, settings)

    async with session_factory() as storage:
        regions = await storage.regions.list_active()

    reports = [
        await _region_health(
            region,
            proxy_ref=None,
            health_service=health_service,
            cookie_store=cookie_store,
            settings=settings,
            fix=fix,
            warmer=warmer,
        )
        for region in regions
    ]
    return HealthReport(regions=reports)


async def warm(
    region_codes: list[str] | None,
    *,
    session_factory: SessionFactory | None = None,
    settings: Settings | None = None,
    cookie_store: CookieStore | None = None,
    provider: ProxyProvider | None = None,
    warmer: CookieWarmer | None = None,
) -> int:
    """Warm Ozon cookies for the given regions (default: all active with an Ozon geo entry)."""
    settings = settings or get_settings()
    session_factory = session_factory or make_storage(settings)
    store = cookie_store or make_cookie_store(settings)
    warmer = warmer or CookieWarmer()
    provider = provider or make_proxy_provider(settings)

    async with session_factory() as storage:
        if region_codes:
            regions = []
            for code in region_codes:
                region = await storage.regions.get_by_code(code)
                if region is None:
                    print(f"unknown region: {code}", file=sys.stderr)
                    return 1
                regions.append(region)
        else:
            regions = [r for r in await storage.regions.list_active() if "ozon" in r.geo]

    for region in regions:
        lease = await provider.acquire(region.code)
        warm_if_stale(
            store, warmer, Marketplace.OZON, region, settings.ozon_cookie_ttl_hours, lease.proxy_url
        )
        print(f"  region={region.code}: warmed")
    return 0


def format_report(report: HealthReport) -> str:
    """Render the health report as human-readable text."""
    lines = [f"healthy: {report.healthy}"]
    for r in report.regions:
        lines.append(
            f"  region={r.region_code} cooling_down={r.cooling_down} "
            f"cookie_stale={r.cookie_stale} warmed={r.warmed}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint: default prints the health report (`--fix` warms stale cookies);
    `warm [--region ...]` warms Ozon cookies for one or all regions."""
    parser = argparse.ArgumentParser(
        prog="app.scripts.health", description="Report proxy/cookie health; optionally warm stale cookies"
    )
    parser.add_argument("--fix", action="store_true", help="Warm stale Ozon cookies")
    subparsers = parser.add_subparsers(dest="action")
    warm_parser = subparsers.add_parser("warm", help="Warm Ozon cookies for one or all regions")
    warm_parser.add_argument(
        "--region",
        action="append",
        default=None,
        help="Region code; repeatable (default: all active regions with an Ozon geo entry)",
    )
    args = parser.parse_args(argv)

    if args.action == "warm":
        return asyncio.run(warm(args.region))

    report = asyncio.run(run(fix=args.fix))
    print(format_report(report))
    if not report.healthy:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
