"""app.cli — pure-dispatcher tests: every subcommand delegates to a script, no logic in cli.py."""

from unittest.mock import patch

from app import cli
from app.scripts import control_panel, health, orchestrator, ozon, panel, parameters, report, wb


def _patched(module, name):
    async def _noop(*args, **kwargs):
        return 0

    return patch.object(module, name, side_effect=_noop)


def test_healthcheck_delegates_to_parameters() -> None:
    with _patched(parameters, "healthcheck") as mock_fn:
        result = cli.main(["healthcheck"])

    assert result == 0
    mock_fn.assert_called_once_with()


def test_import_products_delegates_to_control_panel(tmp_path) -> None:
    path = tmp_path / "products.json"
    path.write_text("[]")

    with _patched(control_panel, "import_products") as mock_fn:
        result = cli.main(["import-products", str(path)])

    assert result == 0
    mock_fn.assert_called_once_with(str(path))


def test_import_regions_delegates_to_control_panel(tmp_path) -> None:
    path = tmp_path / "regions.json"
    path.write_text("[]")

    with _patched(control_panel, "import_regions") as mock_fn:
        result = cli.main(["import-regions", str(path)])

    assert result == 0
    mock_fn.assert_called_once_with(str(path))


def test_measure_wb_delegates_to_wb_script() -> None:
    with _patched(wb, "run") as mock_fn:
        result = cli.main(["measure-wb", "--region", "msk", "--sku", "123"])

    assert result == 0
    mock_fn.assert_called_once_with(["msk"], "123")


def test_measure_ozon_delegates_to_ozon_script() -> None:
    with _patched(ozon, "run") as mock_fn:
        result = cli.main(["measure-ozon", "--region", "msk", "--sku", "123"])

    assert result == 0
    mock_fn.assert_called_once_with(["msk"], "123")


def test_warm_ozon_delegates_to_health_script() -> None:
    with _patched(health, "warm") as mock_fn:
        result = cli.main(["warm-ozon", "--region", "msk"])

    assert result == 0
    mock_fn.assert_called_once_with(["msk"])


def test_run_once_delegates_to_orchestrator() -> None:
    from app.scheduler.runner import RunSummary

    async def _fake_run(*args, **kwargs):
        return RunSummary(run_id=1, stats={"ok": 1})

    with patch.object(orchestrator, "run", side_effect=_fake_run) as mock_fn:
        result = cli.main(["run-once"])

    assert result == 0
    mock_fn.assert_called_once()


def test_serve_delegates_to_orchestrator() -> None:
    with _patched(orchestrator, "serve") as mock_fn:
        result = cli.main(["serve"])

    assert result == 0
    mock_fn.assert_called_once_with()


def test_metrics_delegates_to_report() -> None:
    with _patched(report, "run") as mock_fn:
        result = cli.main(["metrics", "--last"])

    assert result == 0
    mock_fn.assert_called_once_with(None, True)


def test_panel_delegates_to_panel_script() -> None:
    with patch.object(panel, "run", return_value=0) as mock_fn:
        result = cli.main(["panel", "--host", "0.0.0.0", "--port", "9000"])

    assert result == 0
    mock_fn.assert_called_once_with("0.0.0.0", 9000)


def test_cli_module_holds_no_business_logic() -> None:
    """Grep-equivalent guard: cli.py's source references no repo/provider/session symbols."""
    import inspect

    source = inspect.getsource(cli)
    for forbidden in ("Repository", "make_proxy_provider", "get_session", "measure_pair"):
        assert forbidden not in source, f"cli.py should not reference {forbidden!r}"
