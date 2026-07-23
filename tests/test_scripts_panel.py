"""app.scripts.panel — argv smoke test + app-factory routes (no socket binding)."""

import pytest

from app.panel import create_app
from app.scripts import panel


def test_main_help_smoke() -> None:
    with pytest.raises(SystemExit) as exc_info:
        panel.main(["--help"])
    assert exc_info.value.code == 0


def test_create_app_builds_expected_routes() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/health" in paths
    assert "/run" in paths
    assert "/tab/{name}" in paths
