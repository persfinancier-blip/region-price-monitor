"""should_alert, LogAlerter, WebhookAlerter — no live network."""

import logging

import pytest

from app.obs.alerts import Alert, LogAlerter, WebhookAlerter, make_alerter, should_alert
from app.obs.metrics import RunMetrics


class _Settings:
    def __init__(self, alerter: str, alert_webhook_url: str | None = None) -> None:
        self.alerter = alerter
        self.alert_webhook_url = alert_webhook_url


def _metrics(total: int, success_rate: float) -> RunMetrics:
    return RunMetrics(run_id=1, total=total, success_rate=success_rate)


def test_should_alert_true_below_threshold() -> None:
    assert should_alert(_metrics(10, 0.5), threshold=0.9, min_measures=1) is True


def test_should_alert_false_at_threshold() -> None:
    assert should_alert(_metrics(10, 0.9), threshold=0.9, min_measures=1) is False


def test_should_alert_false_above_threshold() -> None:
    assert should_alert(_metrics(10, 0.95), threshold=0.9, min_measures=1) is False


def test_should_alert_false_below_min_measures() -> None:
    assert should_alert(_metrics(1, 0.0), threshold=0.9, min_measures=5) is False


async def test_log_alerter_logs(caplog: pytest.LogCaptureFixture) -> None:
    alerter = LogAlerter()
    alert = Alert(
        kind="success_rate_below_threshold", run_id=42, success_rate=0.5, threshold=0.9, message="m"
    )

    with caplog.at_level(logging.WARNING):
        await alerter.send(alert)

    assert any(r.message == "alert" and getattr(r, "run_id", None) == 42 for r in caplog.records)


async def test_webhook_alerter_posts_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json, timeout))

        class _Resp:
            status_code = 200

        return _Resp()

    monkeypatch.setattr("app.obs.alerts.requests.post", fake_post)

    alerter = WebhookAlerter("https://hooks.example.com/alert")
    alert = Alert(
        kind="success_rate_below_threshold", run_id=7, success_rate=0.4, threshold=0.9, message="low"
    )

    await alerter.send(alert)

    assert len(calls) == 1
    url, payload, timeout = calls[0]
    assert url == "https://hooks.example.com/alert"
    assert payload == {
        "kind": "success_rate_below_threshold",
        "run_id": 7,
        "success_rate": 0.4,
        "threshold": 0.9,
        "message": "low",
    }
    assert timeout is not None


async def test_webhook_alerter_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    def fake_post(url, json=None, timeout=None):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr("app.obs.alerts.requests.post", fake_post)

    alerter = WebhookAlerter("https://hooks.example.com/alert")
    alert = Alert(
        kind="success_rate_below_threshold", run_id=7, success_rate=0.4, threshold=0.9, message="low"
    )

    await alerter.send(alert)  # must not raise


def test_make_alerter_log_default() -> None:
    assert isinstance(make_alerter(_Settings("log")), LogAlerter)


def test_make_alerter_webhook_requires_url() -> None:
    with pytest.raises(ValueError, match="alert_webhook_url"):
        make_alerter(_Settings("webhook", None))


def test_make_alerter_webhook_with_url() -> None:
    alerter = make_alerter(_Settings("webhook", "https://hooks.example.com/x"))
    assert isinstance(alerter, WebhookAlerter)


def test_make_alerter_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown alerter"):
        make_alerter(_Settings("carrier-pigeon"))
