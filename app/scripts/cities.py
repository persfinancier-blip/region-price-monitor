"""`cities` script — local settings store for per-city WB/Ozon config (ADR-0008/0011).

A flat JSON file (`settings.city_config_path`) holds a general `defaults`
profile per marketplace plus a `cities` list, each city carrying either
`mode: "inherit"` (use `defaults`) or `mode: "override"` (its own
`enabled`/`proxy`/`interval_min`) per marketplace. `list_effective()` resolves
inherit vs. override and drops disabled (city, marketplace) pairs entirely —
that resolved view is what `app/scripts/control_panel.py::run` consumes to
build the work set. No file yet ⇒ seed once from the `regions` store +
`proxy_map_json`/interval settings (back-compat). No secrets store: proxy
URLs live in the plain file, masked in any printed/logged/HTML output.
"""

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from app.config import Settings, get_settings
from app.proxy.static import parse_proxy_map
from app.storage.factory import make_storage

_MASK = "***"
_MARKETPLACES = ("wb", "ozon")

Mode = Literal["inherit", "override"]


@dataclass(frozen=True)
class MarketplaceDefaults:
    """The general profile for one marketplace — applies to every inheriting city."""

    enabled: bool
    proxy: str | None
    interval_min: int


@dataclass(frozen=True)
class MarketplaceOverride:
    """A city's local override for one marketplace."""

    mode: Mode
    enabled: bool | None = None
    proxy: str | None = None
    interval_min: int | None = None


@dataclass(frozen=True)
class CityConfig:
    """One city's raw config — per-marketplace inherit/override entries."""

    code: str
    name: str
    geo: dict[str, Any]
    wb: MarketplaceOverride
    ozon: MarketplaceOverride


@dataclass(frozen=True)
class CitiesConfig:
    """The whole store: general defaults + the list of configured cities."""

    defaults: dict[str, MarketplaceDefaults]
    cities: list[CityConfig]


@dataclass(frozen=True)
class EffectiveMarketplace:
    """The resolved (inherit-merged) settings for one (city, marketplace) pair."""

    enabled: bool
    proxy: str | None
    interval_min: int
    mode: Mode


@dataclass(frozen=True)
class EffectiveCity:
    """A city plus its resolved per-marketplace settings, disabled pairs dropped."""

    code: str
    name: str
    geo: dict[str, Any]
    marketplaces: dict[str, EffectiveMarketplace]


def mask_proxy(proxy: str | None) -> str | None:
    """Return `None` unmasked, else a fixed mask — never leak proxy credentials."""
    return None if proxy is None else _MASK


def _proxy_host(proxy: str | None) -> str | None:
    if proxy is None:
        return None
    return urlsplit(proxy).hostname or "unknown"


def _default_path(settings: Settings) -> str:
    return settings.city_config_path


def _mp_defaults_from_dict(raw: dict[str, Any]) -> MarketplaceDefaults:
    return MarketplaceDefaults(
        enabled=bool(raw["enabled"]), proxy=raw.get("proxy"), interval_min=int(raw["interval_min"])
    )


def _mp_override_from_dict(raw: dict[str, Any]) -> MarketplaceOverride:
    mode: Mode = "override" if raw.get("mode") == "override" else "inherit"
    return MarketplaceOverride(
        mode=mode,
        enabled=raw.get("enabled"),
        proxy=raw.get("proxy"),
        interval_min=raw.get("interval_min"),
    )


def _city_from_dict(raw: dict[str, Any]) -> CityConfig:
    return CityConfig(
        code=raw["code"],
        name=raw["name"],
        geo=raw.get("geo", {}),
        wb=_mp_override_from_dict(raw.get("wb", {})),
        ozon=_mp_override_from_dict(raw.get("ozon", {})),
    )


def _config_from_dict(raw: dict[str, Any]) -> CitiesConfig:
    defaults = {mp: _mp_defaults_from_dict(raw["defaults"][mp]) for mp in _MARKETPLACES}
    cities = [_city_from_dict(c) for c in raw.get("cities", [])]
    return CitiesConfig(defaults=defaults, cities=cities)


def _mp_defaults_to_dict(d: MarketplaceDefaults) -> dict[str, Any]:
    return {"enabled": d.enabled, "proxy": d.proxy, "interval_min": d.interval_min}


def _mp_override_to_dict(o: MarketplaceOverride) -> dict[str, Any]:
    result: dict[str, Any] = {"mode": o.mode}
    if o.mode == "override":
        result["enabled"] = o.enabled
        result["proxy"] = o.proxy
        result["interval_min"] = o.interval_min
    return result


def _city_to_dict(c: CityConfig) -> dict[str, Any]:
    return {
        "code": c.code,
        "name": c.name,
        "geo": c.geo,
        "wb": _mp_override_to_dict(c.wb),
        "ozon": _mp_override_to_dict(c.ozon),
    }


def _config_to_dict(config: CitiesConfig) -> dict[str, Any]:
    return {
        "defaults": {mp: _mp_defaults_to_dict(config.defaults[mp]) for mp in _MARKETPLACES},
        "cities": [_city_to_dict(c) for c in config.cities],
    }


def _default_defaults() -> dict[str, MarketplaceDefaults]:
    return {mp: MarketplaceDefaults(enabled=True, proxy=None, interval_min=360) for mp in _MARKETPLACES}


async def _seed_from_regions(settings: Settings, storage_factory: Any = None) -> CitiesConfig:
    """Back-compat: no `city_config_path` file ⇒ seed cities from `regions` +
    `proxy_map_json`, so existing behaviour (all active regions, WB always, Ozon
    only with an `ozon` geo entry) is preserved until the owner edits the store."""
    proxy_map = parse_proxy_map(settings.proxy_map_json)
    storage_factory = storage_factory or make_storage(settings)
    async with storage_factory() as storage:
        regions = await storage.regions.list_active()

    cities = []
    for region in regions:
        proxy = proxy_map.get(region.code, settings.proxy_url)
        has_ozon = "ozon" in region.geo
        cities.append(
            CityConfig(
                code=region.code,
                name=region.name,
                geo=region.geo,
                wb=MarketplaceOverride(mode="override", enabled=True, proxy=proxy, interval_min=360)
                if proxy
                else MarketplaceOverride(mode="inherit"),
                ozon=(
                    (
                        MarketplaceOverride(mode="override", enabled=True, proxy=proxy, interval_min=360)
                        if proxy
                        else MarketplaceOverride(mode="inherit")
                    )
                    if has_ozon
                    else MarketplaceOverride(mode="override", enabled=False, proxy=None, interval_min=360)
                ),
            )
        )

    return CitiesConfig(defaults=_default_defaults(), cities=cities)


async def load(settings: Settings | None = None, storage_factory: Any = None) -> CitiesConfig:
    """Load the store from `settings.city_config_path`; seed from `regions` if absent."""
    settings = settings or get_settings()
    path = _default_path(settings)
    if not os.path.exists(path):
        return await _seed_from_regions(settings, storage_factory)

    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return _config_from_dict(raw)


def save(config: CitiesConfig, settings: Settings | None = None) -> None:
    """Persist the store atomically (temp file + `os.replace`)."""
    settings = settings or get_settings()
    path = _default_path(settings)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(_config_to_dict(config), fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _resolve(defaults: MarketplaceDefaults, override: MarketplaceOverride) -> EffectiveMarketplace:
    if override.mode == "inherit":
        return EffectiveMarketplace(
            enabled=defaults.enabled, proxy=defaults.proxy, interval_min=defaults.interval_min, mode="inherit"
        )
    return EffectiveMarketplace(
        enabled=bool(override.enabled),
        proxy=override.proxy,
        interval_min=override.interval_min if override.interval_min is not None else defaults.interval_min,
        mode="override",
    )


def list_effective(config: CitiesConfig) -> list[EffectiveCity]:
    """Resolve inherit vs. override per (city, marketplace); drop disabled pairs."""
    result = []
    for city in config.cities:
        marketplaces = {}
        for mp, override in (("wb", city.wb), ("ozon", city.ozon)):
            effective = _resolve(config.defaults[mp], override)
            if effective.enabled:
                marketplaces[mp] = effective
        result.append(EffectiveCity(code=city.code, name=city.name, geo=city.geo, marketplaces=marketplaces))
    return result


def add_city(
    config: CitiesConfig, *, code: str, name: str, geo: dict[str, Any] | None = None
) -> CitiesConfig:
    """Add a city, both marketplaces `inherit` by default; no-op if the code exists."""
    if any(c.code == code for c in config.cities):
        return config
    new_city = CityConfig(
        code=code,
        name=name,
        geo=geo or {},
        wb=MarketplaceOverride(mode="inherit"),
        ozon=MarketplaceOverride(mode="inherit"),
    )
    return CitiesConfig(defaults=config.defaults, cities=[*config.cities, new_city])


def set_marketplace(
    config: CitiesConfig,
    *,
    code: str,
    marketplace: str,
    mode: Mode,
    enabled: bool | None = None,
    proxy: str | None = None,
    interval_min: int | None = None,
    keep_proxy_if_empty: bool = False,
) -> CitiesConfig:
    """Set a city's per-marketplace mode/override. `keep_proxy_if_empty=True` with
    `proxy=None` keeps the currently-stored proxy instead of blanking it."""
    cities = []
    for city in config.cities:
        if city.code != code:
            cities.append(city)
            continue
        current = city.wb if marketplace == "wb" else city.ozon
        resolved_proxy = proxy
        if keep_proxy_if_empty and proxy is None:
            resolved_proxy = current.proxy
        new_override = MarketplaceOverride(
            mode=mode,
            enabled=enabled if mode == "override" else None,
            proxy=resolved_proxy if mode == "override" else None,
            interval_min=interval_min if mode == "override" else None,
        )
        if marketplace == "wb":
            cities.append(
                CityConfig(code=city.code, name=city.name, geo=city.geo, wb=new_override, ozon=city.ozon)
            )
        else:
            cities.append(
                CityConfig(code=city.code, name=city.name, geo=city.geo, wb=city.wb, ozon=new_override)
            )
    return CitiesConfig(defaults=config.defaults, cities=cities)


def set_enabled(config: CitiesConfig, *, code: str, marketplace: str, enabled: bool) -> CitiesConfig:
    """Toggle a marketplace on/off for a city, switching it to `override` if needed."""
    for city in config.cities:
        if city.code != code:
            continue
        current = city.wb if marketplace == "wb" else city.ozon
        if current.mode == "override":
            return set_marketplace(
                config,
                code=code,
                marketplace=marketplace,
                mode="override",
                enabled=enabled,
                proxy=current.proxy,
                interval_min=current.interval_min,
            )
        defaults = config.defaults[marketplace]
        return set_marketplace(
            config,
            code=code,
            marketplace=marketplace,
            mode="override",
            enabled=enabled,
            proxy=defaults.proxy,
            interval_min=defaults.interval_min,
        )
    return config


def remove_city(config: CitiesConfig, *, code: str) -> CitiesConfig:
    """Deactivate/drop a city from the config — never touches measurement history."""
    return CitiesConfig(defaults=config.defaults, cities=[c for c in config.cities if c.code != code])


def format_report(config: CitiesConfig) -> str:
    """Render the store — general defaults + each city's effective settings, proxy masked."""
    lines = ["defaults:"]
    for mp in _MARKETPLACES:
        d = config.defaults[mp]
        lines.append(f"  {mp}: enabled={d.enabled} proxy={mask_proxy(d.proxy)} interval_min={d.interval_min}")
    lines.append("cities:")
    for city in list_effective(config):
        parts = []
        for mp, eff in city.marketplaces.items():
            parts.append(f"{mp}(proxy={mask_proxy(eff.proxy)},interval={eff.interval_min},mode={eff.mode})")
        lines.append(f"  {city.code}: {' '.join(parts) or '-'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint: `list` (default) / `add` / `set` / `enable` / `disable` / `remove`."""
    parser = argparse.ArgumentParser(prog="app.scripts.cities", description="Manage the local cities store")
    subparsers = parser.add_subparsers(dest="action")
    subparsers.add_parser("list", help="Print defaults + effective per-city settings (default)")

    add_parser = subparsers.add_parser("add", help="Add a city")
    add_parser.add_argument("code")
    add_parser.add_argument("name")

    set_parser = subparsers.add_parser("set", help="Set a city's marketplace mode/override")
    set_parser.add_argument("code")
    set_parser.add_argument("marketplace", choices=_MARKETPLACES)
    set_parser.add_argument("mode", choices=["inherit", "override"])
    set_parser.add_argument("--proxy", default=None)
    set_parser.add_argument("--interval-min", type=int, default=None)
    set_parser.add_argument("--enabled", type=lambda s: s.lower() != "false", default=True)

    for verb in ("enable", "disable"):
        p = subparsers.add_parser(verb, help=f"{verb.capitalize()} a marketplace for a city")
        p.add_argument("code")
        p.add_argument("marketplace", choices=_MARKETPLACES)

    remove_parser = subparsers.add_parser("remove", help="Remove a city from the config")
    remove_parser.add_argument("code")

    args = parser.parse_args(argv)
    settings = get_settings()

    import asyncio

    config = asyncio.run(load(settings))

    if args.action == "add":
        config = add_city(config, code=args.code, name=args.name)
        save(config, settings)
    elif args.action == "set":
        config = set_marketplace(
            config,
            code=args.code,
            marketplace=args.marketplace,
            mode=args.mode,
            enabled=args.enabled,
            proxy=args.proxy,
            interval_min=args.interval_min,
        )
        save(config, settings)
    elif args.action in ("enable", "disable"):
        config = set_enabled(
            config, code=args.code, marketplace=args.marketplace, enabled=args.action == "enable"
        )
        save(config, settings)
    elif args.action == "remove":
        config = remove_city(config, code=args.code)
        save(config, settings)

    print(format_report(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
