"""Ozon collector — `curl_cffi` impersonation + warmed cookies (ADR-0005).

Plain `requests` gets a 403 from Ozon's JA3/TLS fingerprinting; `curl_cffi` with
`impersonate="chrome"` is mandatory. Region is carried by the warmed cookie by
default (`proxy_url=None`, direct fetch); a city may additionally route through a
personal proxy (hybrid model) via the existing `StaticProxyProvider`.
"""

from typing import Any, cast

from curl_cffi import requests as curl_requests

from app.collectors.base import PriceObservation
from app.collectors.fingerprint import ozon_impersonate
from app.collectors.ozon_parse import OzonParseError, parse_ozon
from app.config import get_settings
from app.cookies.base import CookieStore, is_stale
from app.enums import Marketplace
from app.models import Product, Region
from app.proxy.base import proxy_url_to_requests_dict


class OzonCookiesUnavailable(RuntimeError):
    """No warmed cookie bundle for this (marketplace, region), or it is stale.

    Raised before any network call — the CLI turns this into a warm request,
    not a failed collection attempt.
    """


class OzonCollectionError(ValueError):
    """An Ozon collection attempt failed; carries enough context to classify the Outcome."""

    def __init__(self, message: str, *, status_code: int | None = None, anti_bot: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.anti_bot = anti_bot


class OzonCollector:
    """Reads current price/availability for an Ozon product from the composer-api endpoint."""

    marketplace = Marketplace.OZON

    def __init__(self, cookie_store: CookieStore) -> None:
        self._cookie_store = cookie_store

    def collect(self, product: Product, region: Region, proxy_url: str | None = None) -> PriceObservation:
        settings = get_settings()
        bundle = self._cookie_store.load(Marketplace.OZON, region.code)
        if bundle is None or is_stale(bundle, settings.ozon_cookie_ttl_hours):
            raise OzonCookiesUnavailable(
                f"no fresh warmed cookies for Ozon region={region.code} — run warm-ozon first"
            )

        cookies = {c["name"]: c["value"] for c in bundle.storage_state.get("cookies", [])}
        response = curl_requests.get(
            settings.ozon_api_url,
            params={"url": f"/product/{product.sku}/"},
            impersonate=cast(Any, ozon_impersonate(region, settings)),
            cookies=cookies,
            proxies=cast(Any, proxy_url_to_requests_dict(proxy_url)),
            timeout=settings.http_timeout_s,
        )

        body = response.text.strip()
        if response.status_code != 200 or not body.startswith("{"):
            raise OzonCollectionError(
                f"Ozon composer-api request failed: HTTP {response.status_code} for sku={product.sku},"
                f" region={region.code}",
                status_code=response.status_code,
                anti_bot=response.status_code == 200,
            )
        try:
            raw_json: Any = response.json  # untyped in curl_cffi's stubs
            payload: dict[str, Any] = raw_json()
            return parse_ozon(payload)
        except OzonParseError as exc:
            raise OzonCollectionError(
                f"Ozon composer-api parse failed for sku={product.sku}, region={region.code}: {exc}",
                status_code=response.status_code,
                anti_bot=True,
            ) from exc
