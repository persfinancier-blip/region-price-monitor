"""app.panel — `POST /run` invokes orchestrator.run once, guards overlapping runs."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.panel import app as panel_app


def _client() -> TestClient:
    return TestClient(panel_app.create_app())


def test_run_now_invokes_orchestrator_once() -> None:
    panel_app._run_state["running"] = False
    fake_run = AsyncMock(return_value=None)

    with patch.object(panel_app.orchestrator, "run", fake_run):
        response = _client().post("/run")

    assert response.status_code == 200
    assert "Запуск начат" in response.text
    fake_run.assert_awaited_once()
    panel_app._run_state["running"] = False


def test_run_now_guards_overlapping_runs() -> None:
    panel_app._run_state["running"] = True
    fake_run = AsyncMock(return_value=None)

    with patch.object(panel_app.orchestrator, "run", fake_run):
        response = _client().post("/run")

    assert response.status_code == 200
    assert "уже выполняется" in response.text
    fake_run.assert_not_awaited()
    panel_app._run_state["running"] = False
