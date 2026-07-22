"""Command-line entrypoint for region-price-monitor."""

import argparse
import asyncio
import sys

from app.db import healthcheck


async def _healthcheck() -> int:
    try:
        ok = await healthcheck()
    except Exception as exc:  # noqa: BLE001 — surfaced to the operator as a CLI failure
        print(f"DB healthcheck FAILED: {exc}", file=sys.stderr)
        return 1
    if ok:
        print("OK")
        return 0
    print("DB healthcheck FAILED: unexpected result", file=sys.stderr)
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="region-price-monitor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("healthcheck", help="Verify database connectivity")

    args = parser.parse_args()

    if args.command == "healthcheck":
        sys.exit(asyncio.run(_healthcheck()))


if __name__ == "__main__":
    main()
