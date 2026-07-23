"""`parameters` script — resolved connection/runtime parameters (ADR-0008/0009).

Wraps `app.config.Settings` + the storage factory (`app.storage.factory.make_storage`,
local or Postgres per `settings.storage_backend`) + resolved endpoints/paths
(WB card URL, Ozon API URL, cookie store dir) into a single typed snapshot
other scripts consume. Standalone, it prints the resolved parameters with
secrets/credentials masked.
"""

import argparse
import sys
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.scheduler.runner import SessionFactory
from app.storage.factory import make_storage

_MASK = "***"


@dataclass(frozen=True)
class Parameters:
    """A resolved snapshot of settings + storage factory + endpoints/paths."""

    settings: Settings
    session_factory: SessionFactory
    wb_card_url: str
    ozon_api_url: str
    cookie_store_dir: str


def run() -> Parameters:
    """Resolve current settings/storage factory/endpoints into a `Parameters` snapshot."""
    settings = get_settings()
    return Parameters(
        settings=settings,
        session_factory=make_storage(settings),
        wb_card_url=settings.wb_card_url,
        ozon_api_url=settings.ozon_api_url,
        cookie_store_dir=settings.cookie_store_dir,
    )


async def healthcheck(settings: Settings | None = None) -> int:
    """Verify storage connectivity: local dir is writable, or Postgres `SELECT 1` succeeds."""
    settings = settings or get_settings()

    if settings.storage_backend == "local":
        import os

        try:
            os.makedirs(settings.local_state_dir, exist_ok=True)
            probe = os.path.join(settings.local_state_dir, ".healthcheck")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(probe)
        except OSError as exc:
            print(f"local storage healthcheck FAILED: {exc}", file=sys.stderr)
            return 1
        print("OK")
        return 0

    from app.db import healthcheck as db_healthcheck

    try:
        ok = await db_healthcheck()
    except Exception as exc:  # noqa: BLE001 — surface any connectivity failure to the operator
        print(f"DB healthcheck FAILED: {exc}", file=sys.stderr)
        return 1
    if ok:
        print("OK")
        return 0
    print("DB healthcheck FAILED: unexpected result", file=sys.stderr)
    return 1


def _masked_proxy_url(proxy_url: str | None) -> str | None:
    return None if proxy_url is None else _MASK


def format_report(params: Parameters) -> str:
    """Render the resolved parameters as human-readable text, secrets masked."""
    settings = params.settings
    lines = [
        f"database_url={_MASK}",
        f"schedule_cron={settings.schedule_cron}",
        f"max_concurrency={settings.max_concurrency}",
        f"proxy_provider={settings.proxy_provider}",
        f"proxy_url={_masked_proxy_url(settings.proxy_url)}",
        f"proxy_map_json={_MASK if settings.proxy_map_json else None}",
        f"wb_card_url={params.wb_card_url}",
        f"ozon_api_url={params.ozon_api_url}",
        f"cookie_store_dir={params.cookie_store_dir}",
        f"alert_webhook_url={_MASK if settings.alert_webhook_url else None}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint: default prints resolved parameters (secrets masked);
    `--check` verifies DB connectivity instead."""
    import asyncio

    parser = argparse.ArgumentParser(prog="app.scripts.parameters", description="Print resolved parameters")
    parser.add_argument("--check", action="store_true", help="Verify DB connectivity instead")
    args = parser.parse_args(argv)

    if args.check:
        return asyncio.run(healthcheck())

    params = run()
    print(format_report(params))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
