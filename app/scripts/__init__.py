"""Standalone-runnable script layer (ADR-0008).

Each module here wraps existing `app/*` modules (collectors, proxy, cookies,
scheduler, repositories) behind a typed `run(...)` and a `main(argv)` CLI, so
it can run headless on its own (`python -m app.scripts.<name>`) or be composed
by `app/scripts/orchestrator.py` / delegated to by the thin `app/cli.py` shell.
No business logic is duplicated — see the module docstrings for what each
script wraps.
"""
