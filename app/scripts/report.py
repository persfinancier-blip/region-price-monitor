"""`report` script — print a run's metrics (ADR-0008).

Wraps `app.obs.metrics` (`compute_run_metrics`/`to_prometheus`) to resolve a
run (by `--run <id>` or `--last`) and print the human summary + Prometheus
text, reproducing the former `app/cli.py::_metrics` behaviour exactly (also
emits the structured `metrics` log line). Named `report` to avoid colliding
with `app/obs/metrics.py`.
"""

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from app.db import get_session
from app.models import Run
from app.obs.metrics import compute_run_metrics, to_prometheus
from app.scheduler.runner import SessionFactory


async def run(run_id: int | None, last: bool, *, session_factory: SessionFactory = get_session) -> int:
    """Resolve `--run`/`--last`, print the metrics summary + Prometheus text, log structured `metrics`."""
    async with session_factory() as session:
        if last:
            result = await session.execute(select(Run).order_by(Run.id.desc()).limit(1))
            run_row = result.scalar_one_or_none()
            if run_row is None:
                print("no runs found", file=sys.stderr)
                return 1
            target_run_id = run_row.id
        elif run_id is not None:
            target_run_id = run_id
        else:
            print("either --run or --last is required", file=sys.stderr)
            return 1

        metrics = await compute_run_metrics(session, target_run_id)

    print(
        f"run {metrics.run_id}: total={metrics.total} "
        f"success_rate={metrics.success_rate:.3f} ban_rate={metrics.ban_rate:.3f} "
        f"error_rate={metrics.error_rate:.3f} avg_duration_ms={metrics.avg_duration_ms:.1f} "
        f"attempts_per_success={metrics.attempts_per_success:.2f}"
    )
    print(to_prometheus(metrics), end="")
    logging.getLogger(__name__).info(
        "metrics",
        extra={
            "run_id": metrics.run_id,
            "total": metrics.total,
            "success_rate": metrics.success_rate,
            "ban_rate": metrics.ban_rate,
            "error_rate": metrics.error_rate,
            "avg_duration_ms": metrics.avg_duration_ms,
            "attempts_per_success": metrics.attempts_per_success,
        },
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint mirroring the `metrics` CLI command's argv surface."""
    parser = argparse.ArgumentParser(
        prog="app.scripts.report", description="Print a run's metrics (human summary + Prometheus text)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", type=int, default=None, dest="run_id", help="Run id")
    group.add_argument("--last", action="store_true", help="Most recent run")
    args = parser.parse_args(argv)

    return asyncio.run(run(args.run_id, args.last))


if __name__ == "__main__":
    raise SystemExit(main())
