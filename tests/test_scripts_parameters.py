"""app.scripts.parameters — unit tests, no network/DB (secrets masked in output)."""

from unittest.mock import patch

from app.config import Settings
from app.scripts import parameters


def test_run_returns_resolved_parameters() -> None:
    params = parameters.run()

    assert params.wb_card_url == params.settings.wb_card_url
    assert params.ozon_api_url == params.settings.ozon_api_url
    assert params.cookie_store_dir == params.settings.cookie_store_dir
    assert callable(params.session_factory)


def test_format_report_masks_secrets() -> None:
    settings = Settings(
        proxy_url="http://user:pass@proxy.example:8080",
        proxy_map_json='{"msk": "http://user:pass@proxy.example:8080"}',
        alert_webhook_url="https://hooks.example/secret-token",
    )
    params = parameters.Parameters(
        settings=settings,
        session_factory=lambda: None,  # type: ignore[arg-type,return-value]
        wb_card_url=settings.wb_card_url,
        ozon_api_url=settings.ozon_api_url,
        cookie_store_dir=settings.cookie_store_dir,
    )

    report = parameters.format_report(params)

    assert "user:pass" not in report
    assert "secret-token" not in report
    assert "database_url=***" in report
    assert "proxy_url=***" in report


def test_main_help_smoke() -> None:
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        parameters.main(["--help"])
    assert exc_info.value.code == 0


def test_main_prints_report(capsys) -> None:
    exit_code = parameters.main([])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "wb_card_url=" in captured.out


async def test_healthcheck_ok_prints_ok(capsys) -> None:
    with patch("app.db.healthcheck", return_value=True):
        result = await parameters.healthcheck()

    assert result == 0
    assert "OK" in capsys.readouterr().out


async def test_healthcheck_failure_exits_1(capsys) -> None:
    with patch("app.db.healthcheck", return_value=False):
        result = await parameters.healthcheck()

    assert result == 1
    assert "FAILED" in capsys.readouterr().err


def test_main_check_dispatches_to_healthcheck() -> None:
    async def _ok():
        return 0

    with patch.object(parameters, "healthcheck", side_effect=_ok) as mock_healthcheck:
        result = parameters.main(["--check"])

    assert result == 0
    mock_healthcheck.assert_called_once_with()
