"""Success-rate alert seam — mirrors the ProxyProvider pattern (ADR-0007)."""

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import requests

from app.obs.metrics import RunMetrics

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

_WEBHOOK_TIMEOUT_S = 10


@dataclass(frozen=True)
class Alert:
    """A single alert event — no money, no secrets."""

    kind: str
    run_id: int
    success_rate: float
    threshold: float
    message: str


class Alerter(Protocol):
    """Deliver an `Alert` somewhere. Failure must never abort the run."""

    async def send(self, alert: Alert) -> None:
        """Deliver the alert."""
        ...


class LogAlerter:
    """Default alerter — structured WARN/ERROR to the log. Needs no config."""

    async def send(self, alert: Alert) -> None:
        """Log the alert as a structured warning."""
        logger.warning(
            "alert",
            extra={
                "kind": alert.kind,
                "run_id": alert.run_id,
                "success_rate": alert.success_rate,
                "threshold": alert.threshold,
                "alert_message": alert.message,
            },
        )


class WebhookAlerter:
    """Vendor-agnostic webhook alerter — POSTs the alert as JSON. Opt-in via a configured URL."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def send(self, alert: Alert) -> None:
        """POST the alert; log and swallow any failure — never abort the run."""

        def _post() -> None:
            requests.post(
                self._url,
                json={
                    "kind": alert.kind,
                    "run_id": alert.run_id,
                    "success_rate": alert.success_rate,
                    "threshold": alert.threshold,
                    "message": alert.message,
                },
                timeout=_WEBHOOK_TIMEOUT_S,
            )

        try:
            await asyncio.to_thread(_post)
        except requests.RequestException as exc:
            logger.error("webhook alert delivery failed", extra={"run_id": alert.run_id, "error": str(exc)})


def should_alert(metrics: RunMetrics, threshold: float, min_measures: int) -> bool:
    """True when the run is large enough to judge and its success rate is below threshold."""
    return metrics.total >= min_measures and metrics.success_rate < threshold


def make_alerter(settings: "Settings") -> Alerter:
    """Factory: pick an Alerter implementation by `settings.alerter` (mirrors `make_proxy_provider`)."""
    if settings.alerter == "log":
        return LogAlerter()
    if settings.alerter == "webhook":
        if not settings.alert_webhook_url:
            raise ValueError("alerter=webhook requires alert_webhook_url")
        return WebhookAlerter(settings.alert_webhook_url)
    raise ValueError(f"unknown alerter: {settings.alerter!r}")
