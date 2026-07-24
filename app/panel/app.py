"""Panel routes (ADR-0008: shell over `app/scripts/*`, no business logic here).

Dashboard reads go through `app/panel/queries.py`, `app.obs.metrics`, and
`app.scripts.control_panel.run`. "Run now" delegates to `app.scripts.orchestrator.run`
as a background task, guarded against overlaps by a simple in-process flag.

The «Куки» tab (ADR-0012, revised ADR-0013) delegates to `app/scripts/cookies.py`; collect
(guided) and refresh (auto-repair by remembered Ozon address) jobs run `warm_all` (a sync
Playwright call) on a worker thread so they don't block the event loop, with per-marketplace
progress tracked in `_cookie_jobs` for the polling `status` view.
"""

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.enums import Marketplace, RunMode
from app.obs.metrics import RunMetrics, compute_run_metrics
from app.panel import queries
from app.scripts import cities as cities_store
from app.scripts import control_panel, orchestrator
from app.scripts import cookies as cookies_script
from app.storage.factory import make_storage

_BASE_DIR = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

_PLACEHOLDER_TABS = {
    "connection": "Параметры подключения",
    "script-editor": "Редактор скриптов",
    "logs": "Логи / история",
}

_run_state: dict[str, bool] = {"running": False}


class _CollectJob:
    """In-process progress state for one marketplace's collect job."""

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self.running = False
        self.steps: list[dict[str, str | None]] = []

    def is_set(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()

    def reset(self) -> None:
        self._cancel_event.clear()
        self.running = True
        self.steps = []

    def on_progress(self, city_code: str, status: str, detail: str | None = None) -> None:
        self.steps.append({"city_code": city_code, "status": status, "detail": detail})


_cookie_jobs: dict[Marketplace, _CollectJob] = {mp: _CollectJob() for mp in Marketplace}


def create_app() -> FastAPI:
    """Build the panel FastAPI app: mounts static assets, registers routes."""
    app = FastAPI(title="Prizma — панель управления")
    app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        storage_factory = make_storage(get_settings())
        async with storage_factory() as storage:
            runs = await queries.recent_runs(storage, limit=10)
            snapshots = await queries.latest_snapshots(storage)
            run_metrics: dict[int, RunMetrics] = {
                run.id: await compute_run_metrics(storage, run.id) for run in runs
            }

        work_set = await control_panel.run()
        cities_config = await cities_store.load(get_settings(), storage_factory)

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
            "defaults": cities_config.defaults,
            "city_configs": cities_config.cities,
            "mask_proxy": cities_store.mask_proxy,
        }
        return _TEMPLATES.TemplateResponse(request, "dashboard.html", context)

    @app.post("/cities")
    async def add_city(
        code: str = Form(...), name: str = Form(...), geo_ozon: str = Form("")
    ) -> RedirectResponse:
        settings = get_settings()
        storage_factory = make_storage(settings)
        config = await cities_store.load(settings, storage_factory)
        geo = {"ozon": geo_ozon} if geo_ozon else {}
        config = cities_store.add_city(config, code=code, name=name, geo=geo)
        cities_store.save(config, settings)
        return RedirectResponse("/", status_code=303)

    @app.post("/cities/{code}/delete")
    async def delete_city(code: str) -> RedirectResponse:
        settings = get_settings()
        storage_factory = make_storage(settings)
        config = await cities_store.load(settings, storage_factory)
        config = cities_store.remove_city(config, code=code)
        cities_store.save(config, settings)
        return RedirectResponse("/", status_code=303)

    @app.post("/cities/{code}/{mp}")
    async def set_city_marketplace(
        code: str,
        mp: str,
        mode: str = Form(...),
        enabled: bool = Form(False),
        proxy: str = Form(""),
        interval_min: int = Form(360),
    ) -> RedirectResponse:
        settings = get_settings()
        storage_factory = make_storage(settings)
        config = await cities_store.load(settings, storage_factory)
        config = cities_store.set_marketplace(
            config,
            code=code,
            marketplace=mp,
            mode="override" if mode == "override" else "inherit",
            enabled=enabled,
            proxy=proxy or None,
            interval_min=interval_min,
            keep_proxy_if_empty=True,
        )
        cities_store.save(config, settings)
        return RedirectResponse("/", status_code=303)

    @app.post("/run")
    async def run_now(background_tasks: BackgroundTasks) -> HTMLResponse:
        if not _run_state["running"]:
            _run_state["running"] = True
            background_tasks.add_task(_run_and_release)
            message = "Запуск начат"
        else:
            message = "Прогон уже выполняется"
        return HTMLResponse(f'<p id="run-status">{message}</p>')

    @app.get("/tab/cookies", response_class=HTMLResponse)
    async def cookies_tab(request: Request) -> HTMLResponse:
        settings = get_settings()
        config = await cities_store.load(settings)
        health = await cookies_script.status(settings=settings)
        jobs = {mp.value: {"running": job.running, "steps": job.steps} for mp, job in _cookie_jobs.items()}
        context = {
            "active_tab": "cookies",
            "tabs": _tab_list(),
            "cities": config.cities,
            "health": health,
            "jobs": jobs,
        }
        return _TEMPLATES.TemplateResponse(request, "cookies.html", context)

    @app.post("/cookies/{mp}/collect")
    async def collect_cookies(mp: str, background_tasks: BackgroundTasks) -> HTMLResponse:
        marketplace = Marketplace(mp)
        job = _cookie_jobs[marketplace]
        if not job.running:
            job.reset()
            background_tasks.add_task(_collect_and_release, marketplace, job)
            message = "Сбор запущен"
        else:
            message = "Сбор уже выполняется"
        return HTMLResponse(f'<p id="collect-status-{mp}">{message}</p>')

    @app.post("/cookies/{mp}/refresh")
    async def refresh_cookies(mp: str, background_tasks: BackgroundTasks) -> HTMLResponse:
        marketplace = Marketplace(mp)
        job = _cookie_jobs[marketplace]
        if not job.running:
            job.reset()
            background_tasks.add_task(_refresh_and_release, marketplace, job)
            message = "Обновление запущено"
        else:
            message = "Сбор уже выполняется"
        return HTMLResponse(f'<p id="collect-status-{mp}">{message}</p>')

    @app.get("/cookies/status")
    async def cookies_status() -> dict[str, Any]:
        return {mp.value: {"running": job.running, "steps": job.steps} for mp, job in _cookie_jobs.items()}

    @app.post("/cookies/{mp}/{city}")
    async def set_manual_cookie(
        mp: str, city: str, raw: str = Form(...), address_label: str = Form("")
    ) -> RedirectResponse:
        marketplace = Marketplace(mp)
        storage_state = json.loads(raw) if raw else {}
        cookies_script.set_manual(
            marketplace, city, storage_state, settings=get_settings(), address_label=address_label or None
        )
        return RedirectResponse("/tab/cookies", status_code=303)

    @app.post("/cookies/{mp}/{city}/clear")
    async def clear_cookie(mp: str, city: str) -> RedirectResponse:
        marketplace = Marketplace(mp)
        cookies_script.clear(marketplace, city, settings=get_settings())
        return RedirectResponse("/tab/cookies", status_code=303)

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


async def _collect_and_release(marketplace: Marketplace, job: "_CollectJob") -> None:
    try:
        await cookies_script.collect(marketplace, cancel=job, on_progress=job.on_progress)
    finally:
        job.running = False


async def _refresh_and_release(marketplace: Marketplace, job: "_CollectJob") -> None:
    try:
        await cookies_script.refresh(marketplace, cancel=job, on_progress=job.on_progress)
    finally:
        job.running = False


def _tab_list() -> list[dict[str, str]]:
    tabs = [
        {"key": "dashboard", "label": "Панель управления", "href": "/"},
        {"key": "cookies", "label": "Куки", "href": "/tab/cookies"},
    ]
    tabs += [{"key": key, "label": label, "href": f"/tab/{key}"} for key, label in _PLACEHOLDER_TABS.items()]
    return tabs
