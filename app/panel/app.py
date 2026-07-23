"""Panel routes (ADR-0008: shell over `app/scripts/*`, no business logic here).

Dashboard reads go through `app/panel/queries.py`, `app.obs.metrics`, and
`app.scripts.control_panel.run`. "Run now" delegates to `app.scripts.orchestrator.run`
as a background task, guarded against overlaps by a simple in-process flag.
"""

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import get_session
from app.enums import RunMode
from app.obs.metrics import RunMetrics, compute_run_metrics
from app.panel import queries
from app.scripts import control_panel, orchestrator

_BASE_DIR = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

_PLACEHOLDER_TABS = {
    "cookies": "Куки",
    "connection": "Параметры подключения",
    "script-editor": "Редактор скриптов",
    "logs": "Логи / история",
}

_run_state: dict[str, bool] = {"running": False}


def create_app() -> FastAPI:
    """Build the panel FastAPI app: mounts static assets, registers routes."""
    app = FastAPI(title="Prizma — панель управления")
    app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        async with get_session() as session:
            runs = await queries.recent_runs(session, limit=10)
            snapshots = await queries.latest_snapshots(session)
            run_metrics: dict[int, RunMetrics] = {
                run.id: await compute_run_metrics(session, run.id) for run in runs
            }

        work_set = await control_panel.run()

        latest_metrics = run_metrics.get(runs[0].id) if runs else None
        context = {
            "active_tab": "dashboard",
            "tabs": _tab_list(),
            "is_running": _run_state["running"],
            "last_run": runs[0] if runs else None,
            "last_metrics": latest_metrics,
            "runs": runs,
            "run_metrics": run_metrics,
            "snapshots": snapshots,
            "cities": work_set.cities,
        }
        return _TEMPLATES.TemplateResponse(request, "dashboard.html", context)

    @app.post("/run")
    async def run_now(background_tasks: BackgroundTasks) -> HTMLResponse:
        if not _run_state["running"]:
            _run_state["running"] = True
            background_tasks.add_task(_run_and_release)
            message = "Запуск начат"
        else:
            message = "Прогон уже выполняется"
        return HTMLResponse(f'<p id="run-status">{message}</p>')

    @app.get("/tab/{name}", response_class=HTMLResponse)
    async def tab(request: Request, name: str) -> HTMLResponse:
        title = _PLACEHOLDER_TABS.get(name, name)
        context = {
            "active_tab": name,
            "tabs": _tab_list(),
            "title": title,
        }
        return _TEMPLATES.TemplateResponse(request, "placeholder.html", context)

    return app


async def _run_and_release() -> None:
    try:
        await orchestrator.run(mode=RunMode.MANUAL, interactive=False)
    finally:
        _run_state["running"] = False


def _tab_list() -> list[dict[str, str]]:
    tabs = [{"key": "dashboard", "label": "Панель управления", "href": "/"}]
    tabs += [{"key": key, "label": label, "href": f"/tab/{key}"} for key, label in _PLACEHOLDER_TABS.items()]
    return tabs
