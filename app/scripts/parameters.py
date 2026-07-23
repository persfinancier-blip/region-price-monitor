"""`parameters` script — resolved connection/runtime parameters (ADR-0008).

Wraps `app.config.Settings` + the session factory (`app.db.get_session`) +
resolved endpoints/paths (WB card URL, Ozon API URL, cookie store dir) into a
single typed snapshot other scripts consume. Standalone, it prints the
resolved parameters with secrets/credentials masked.
"""

import argparse
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.db import get_session
from app.scheduler.runner import SessionFactory

_MASK = "***"


@dataclass(frozen=True)
class Parameters:
    """A resolved snapshot of settings + session factory + endpoints/paths."""

    settings: Settings
    session_factory: SessionFactory
    wb_card_url: str
    ozon_api_url: str
    cookie_store_dir: str


def run() -> Parameters:
    """Resolve current settings/session factory/endpoints into a `Parameters` snapshot."""
    settings = get_settings()
    return Parameters(
        settings=settings,
        session_factory=get_session,
        wb_card_url=settings.wb_card_url,
        ozon_api_url=settings.ozon_api_url,
        cookie_store_dir=settings.cookie_store_dir,
    )


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
    """Standalone entrypoint: resolve and print parameters with secrets masked."""
    parser = argparse.ArgumentParser(prog="app.scripts.parameters", description="Print resolved parameters")
    parser.parse_args(argv)

    params = run()
    print(format_report(params))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
