"""`orchestrator` script — composes the script pipeline (ADR-0008).

Declares the pipeline as a small in-code `Step`/`Pipeline` structure (name +
callable + `needs` deps), executed in dependency order via a plain
Kahn's-algorithm topological sort. The declared pipeline is
`parameters -> control_panel -> health -> run_once`: parameters resolution
and the health check actually execute; the measure/queue/worker-pool/retry/
alert work is **not** re-implemented here — it is delegated to
`app.scheduler.runner.run_once`, reused as-is. This seam is designed so a
future YAML/JSON pipeline loader (Фаза 8) can replace the hard-coded
`_PIPELINE` below without touching the scripts themselves.
"""

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.enums import RunMode
from app.scheduler.runner import RunSummary, SessionFactory, run_once
from app.scripts import control_panel, health, parameters


@dataclass(frozen=True)
class Step:
    """One pipeline step: a name, an async callable, and its dependency names."""

    name: str
    action: Callable[[], Awaitable[object]]
    needs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pipeline:
    """An ordered set of `Step`s, executed in dependency order."""

    steps: tuple[Step, ...]

    def order(self) -> list[Step]:
        """Topologically sort steps by `needs` (Kahn's algorithm); raises on cycles."""
        by_name = {step.name: step for step in self.steps}
        in_degree = {step.name: len(step.needs) for step in self.steps}
        dependents: dict[str, list[str]] = {step.name: [] for step in self.steps}
        for step in self.steps:
            for dep in step.needs:
                if dep not in by_name:
                    raise ValueError(f"step {step.name!r} needs unknown step {dep!r}")
                dependents[dep].append(step.name)

        ready = [name for name, degree in in_degree.items() if degree == 0]
        ordered: list[Step] = []
        while ready:
            name = ready.pop(0)
            ordered.append(by_name[name])
            for dependent in dependents[name]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    ready.append(dependent)

        if len(ordered) != len(self.steps):
            raise ValueError("pipeline has a dependency cycle")
        return ordered

    async def run(self) -> dict[str, object]:
        """Execute every step in dependency order, collecting each step's result by name."""
        results: dict[str, object] = {}
        for step in self.order():
            results[step.name] = await step.action()
        return results


async def run(
    mode: RunMode = RunMode.MANUAL,
    interactive: bool = False,
    *,
    session_factory: SessionFactory | None = None,
    settings: Settings | None = None,
) -> RunSummary:
    """Run the declared pipeline: parameters -> control_panel -> health -> run_once.

    `run_once` (the existing queue/worker-pool/retry/alert implementation) is
    reused as-is for the actual measurement work; this function only wires the
    earlier steps (parameter resolution, work-set gathering, health check) to
    run before it, and returns the resulting `RunSummary`.
    """
    resolved_settings = settings or get_settings()
    resolved_factory = session_factory or parameters.run().session_factory

    summary_holder: dict[str, RunSummary] = {}

    async def _parameters_step() -> object:
        return parameters.run()

    async def _control_panel_step() -> object:
        return await control_panel.run(resolved_factory, resolved_settings)

    async def _health_step() -> object:
        return await health.run(session_factory=resolved_factory, settings=resolved_settings)

    async def _measure_step() -> object:
        summary = await run_once(resolved_factory, resolved_settings, mode=mode, interactive=interactive)
        summary_holder["summary"] = summary
        return summary

    pipeline = Pipeline(
        steps=(
            Step(name="parameters", action=_parameters_step),
            Step(name="control_panel", action=_control_panel_step, needs=("parameters",)),
            Step(name="health", action=_health_step, needs=("control_panel",)),
            Step(name="measure", action=_measure_step, needs=("health",)),
        )
    )
    await pipeline.run()
    return summary_holder["summary"]


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint: run one full pipeline pass, same output shape as `run-once`."""
    parser = argparse.ArgumentParser(
        prog="app.scripts.orchestrator", description="Run the full measurement pipeline once"
    )
    parser.parse_args(argv)

    summary = asyncio.run(run(mode=RunMode.MANUAL, interactive=sys.stdin.isatty()))
    print(f"run {summary.run_id}: " + ", ".join(f"{k}={v}" for k, v in sorted(summary.stats.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
