"""Command-line entrypoint for region-price-monitor.

Thin shell (ADR-0008): every subcommand delegates to a script under
`app/scripts/` and only parses args / formats output. No business logic lives
here — see `app/scripts/*.py` for the wrapped implementations.
"""

import argparse
import asyncio
import sys

from app.config import get_settings
from app.obs.logging import configure_logging
from app.scripts import cities as cities_script
from app.scripts import control_panel, export, health, orchestrator, ozon, panel, parameters, report, wb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="region-price-monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("healthcheck", help="Verify DB connectivity")

    import_products = subparsers.add_parser("import-products", help="Upsert products from a JSON file")
    import_products.add_argument(
        "file", nargs="?", default=None, help="Path to a products JSON file (default: configured source)"
    )

    import_regions = subparsers.add_parser("import-regions", help="Upsert regions from a JSON file")
    import_regions.add_argument(
        "file", nargs="?", default=None, help="Path to a regions JSON file (default: configured source)"
    )

    measure_wb = subparsers.add_parser(
        "measure-wb", help="Measure current WB prices across regions (via ProxyProvider)"
    )
    measure_wb.add_argument(
        "--region",
        action="append",
        default=None,
        help="Region code; repeatable (default: all active regions)",
    )
    measure_wb.add_argument("--sku", default=None, help="WB SKU (nm); default: all active WB products")

    measure_ozon = subparsers.add_parser(
        "measure-ozon", help="Measure current Ozon prices across regions (via warmed cookies)"
    )
    measure_ozon.add_argument(
        "--region",
        action="append",
        default=None,
        help="Region code; repeatable (default: all active regions with an Ozon geo entry)",
    )
    measure_ozon.add_argument("--sku", default=None, help="Ozon SKU; default: all active Ozon products")

    warm_ozon = subparsers.add_parser("warm-ozon", help="Warm Ozon cookies for one or all regions")
    warm_ozon.add_argument(
        "--region",
        action="append",
        default=None,
        help="Region code; repeatable (default: all active regions with an Ozon geo entry)",
    )

    subparsers.add_parser(
        "run-once", help="Trigger one full run across all active pairs via Scheduler+Queue+worker pool"
    )
    subparsers.add_parser("serve", help="Start the cron daemon (APScheduler) and block")

    panel_parser = subparsers.add_parser("panel", help="Start the local web panel (Dashboard)")
    panel_parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    panel_parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")

    metrics_parser = subparsers.add_parser(
        "metrics", help="Print a run's metrics (human summary + Prometheus text)"
    )
    metrics_group = metrics_parser.add_mutually_exclusive_group(required=True)
    metrics_group.add_argument("--run", type=int, default=None, dest="run_id", help="Run id")
    metrics_group.add_argument("--last", action="store_true", help="Most recent run")

    export_parser = subparsers.add_parser("export", help="Write price snapshots through the configured sink")
    export_parser.add_argument(
        "--preview", action="store_true", help="Print the first mapped rows instead of writing"
    )

    cities_parser = subparsers.add_parser("cities", help="Manage the local cities store")
    cities_sub = cities_parser.add_subparsers(dest="cities_action")
    cities_sub.add_parser("list", help="Print defaults + effective per-city settings (default)")
    cities_add = cities_sub.add_parser("add", help="Add a city")
    cities_add.add_argument("code")
    cities_add.add_argument("name")
    cities_set = cities_sub.add_parser("set", help="Set a city's marketplace mode/override")
    cities_set.add_argument("code")
    cities_set.add_argument("marketplace", choices=["wb", "ozon"])
    cities_set.add_argument("mode", choices=["inherit", "override"])
    cities_set.add_argument("--proxy", default=None)
    cities_set.add_argument("--interval-min", type=int, default=None)
    cities_set.add_argument("--enabled", type=lambda s: s.lower() != "false", default=True)
    for verb in ("enable", "disable"):
        p = cities_sub.add_parser(verb, help=f"{verb.capitalize()} a marketplace for a city")
        p.add_argument("code")
        p.add_argument("marketplace", choices=["wb", "ozon"])
    cities_remove = cities_sub.add_parser("remove", help="Remove a city from the config")
    cities_remove.add_argument("code")

    args = parser.parse_args(argv)

    configure_logging(get_settings())

    async def _run_once() -> int:
        summary = await orchestrator.run(interactive=sys.stdin.isatty())
        print(f"run {summary.run_id}: " + ", ".join(f"{k}={v}" for k, v in sorted(summary.stats.items())))
        return 0

    if args.command == "healthcheck":
        return asyncio.run(parameters.healthcheck())
    if args.command == "import-products":
        if args.file:
            return asyncio.run(control_panel.import_products(args.file))
        return asyncio.run(control_panel.import_products_from_source())
    if args.command == "import-regions":
        if args.file:
            return asyncio.run(control_panel.import_regions(args.file))
        return asyncio.run(control_panel.import_regions_from_source())
    if args.command == "measure-wb":
        return asyncio.run(wb.run(args.region, args.sku))
    if args.command == "measure-ozon":
        return asyncio.run(ozon.run(args.region, args.sku))
    if args.command == "warm-ozon":
        return asyncio.run(health.warm(args.region))
    if args.command == "run-once":
        return asyncio.run(_run_once())
    if args.command == "serve":
        return asyncio.run(orchestrator.serve())
    if args.command == "panel":
        return panel.run(args.host, args.port)
    if args.command == "metrics":
        return asyncio.run(report.run(args.run_id, args.last))
    if args.command == "export":
        return asyncio.run(export.run(preview=args.preview))
    if args.command == "cities":
        cities_argv = [args.cities_action] if args.cities_action else []
        if args.cities_action == "add":
            cities_argv = ["add", args.code, args.name]
        elif args.cities_action == "set":
            cities_argv = ["set", args.code, args.marketplace, args.mode]
            if args.proxy is not None:
                cities_argv += ["--proxy", args.proxy]
            if args.interval_min is not None:
                cities_argv += ["--interval-min", str(args.interval_min)]
            cities_argv += ["--enabled", str(args.enabled)]
        elif args.cities_action in ("enable", "disable"):
            cities_argv = [args.cities_action, args.code, args.marketplace]
        elif args.cities_action == "remove":
            cities_argv = ["remove", args.code]
        return cities_script.main(cities_argv)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
