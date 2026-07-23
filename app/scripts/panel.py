"""`panel` script — starts the local web panel (ADR-0008).

Wraps `app.panel.create_app` with a uvicorn server; the panel itself is a
shell over `app/scripts/*` (no business logic). Local-only by default
(`127.0.0.1`); the panel binds no auth (SPEC-panel §9.6, later slice).
"""

import argparse

import uvicorn

from app.panel import create_app


def run(host: str = "127.0.0.1", port: int = 8000) -> int:
    """Start uvicorn serving the panel app; blocks until interrupted."""
    uvicorn.run(create_app(), host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint: `--host`/`--port` mirror the CLI `panel` subcommand."""
    parser = argparse.ArgumentParser(prog="app.scripts.panel", description="Start the local web panel")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    args = parser.parse_args(argv)

    return run(args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
