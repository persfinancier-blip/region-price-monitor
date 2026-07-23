"""app.panel — the four non-dashboard tabs render a placeholder."""

import pytest
from fastapi.testclient import TestClient

from app.panel import app as panel_app


def _client() -> TestClient:
    return TestClient(panel_app.create_app())


@pytest.mark.parametrize("name", ["cookies", "connection", "script-editor", "logs"])
def test_placeholder_tab_returns_200(name: str) -> None:
    response = _client().get(f"/tab/{name}")
    assert response.status_code == 200
    assert "в разработке" in response.text
