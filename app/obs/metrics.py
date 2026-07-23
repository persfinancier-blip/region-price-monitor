"""Run metrics — derived from existing `runs`/`attempts` data, no new schema (ADR-0007)."""

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Outcome
from app.models import Attempt, MeasureQueueItem


@dataclass(frozen=True)
class RunMetrics:
    """Aggregated outcome/duration metrics for one run."""

    run_id: int
    total: int
    by_outcome: dict[str, int] = field(default_factory=dict)
    success_rate: float = 0.0
    ban_rate: float = 0.0
    error_rate: float = 0.0
    avg_duration_ms: float = 0.0
    attempts_per_success: float = 0.0


def metrics_from_counts(run_id: int, counts: dict[str, int], total_duration_ms: int) -> RunMetrics:
    """Pure arithmetic over per-outcome attempt counts — unit-testable without a DB.

    `attempts_per_success = total / ok`; when `ok == 0` it falls back to `total`
    (worst-case proxy for "infinite cost" without dividing by zero).
    """
    total = sum(counts.values())
    ok = counts.get(Outcome.OK.value, 0)
    ban = counts.get(Outcome.SOFT_BAN.value, 0) + counts.get(Outcome.HARD_BAN.value, 0)
    error = counts.get(Outcome.TIMEOUT.value, 0) + counts.get(Outcome.ERROR.value, 0)

    if total == 0:
        return RunMetrics(run_id=run_id, total=0, by_outcome=dict(counts))

    return RunMetrics(
        run_id=run_id,
        total=total,
        by_outcome=dict(counts),
        success_rate=ok / total,
        ban_rate=ban / total,
        error_rate=error / total,
        avg_duration_ms=total_duration_ms / total,
        attempts_per_success=(total / ok) if ok > 0 else float(total),
    )


async def compute_run_metrics(session: AsyncSession, run_id: int) -> RunMetrics:
    """Aggregate a run's attempts (joined via `measure_queue`) into `RunMetrics`."""
    stmt = (
        select(Attempt.outcome, func.count(), func.coalesce(func.sum(Attempt.duration_ms), 0))
        .join(MeasureQueueItem, Attempt.queue_id == MeasureQueueItem.id)
        .where(MeasureQueueItem.run_id == run_id)
        .group_by(Attempt.outcome)
    )
    result = await session.execute(stmt)

    counts: dict[str, int] = {}
    total_duration_ms = 0
    for outcome, count, duration_sum in result.all():
        counts[outcome.value] = count
        total_duration_ms += int(duration_sum)

    return metrics_from_counts(run_id, counts, total_duration_ms)


def to_prometheus(metrics: RunMetrics) -> str:
    """Render `metrics` as Prometheus text-exposition lines (no `prometheus_client` dependency)."""
    run_label = f'run_id="{metrics.run_id}"'
    lines = [
        f"rpm_run_total{{{run_label}}} {metrics.total}",
        f"rpm_run_success_rate{{{run_label}}} {metrics.success_rate}",
        f"rpm_run_ban_rate{{{run_label}}} {metrics.ban_rate}",
        f"rpm_run_error_rate{{{run_label}}} {metrics.error_rate}",
        f"rpm_run_avg_duration_ms{{{run_label}}} {metrics.avg_duration_ms}",
        f"rpm_run_attempts_per_success{{{run_label}}} {metrics.attempts_per_success}",
    ]
    for outcome, count in sorted(metrics.by_outcome.items()):
        lines.append(f'rpm_run_outcome_total{{{run_label},outcome="{outcome}"}} {count}')
    return "\n".join(lines) + "\n"
