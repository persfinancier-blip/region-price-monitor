"""Anti-bot fingerprint variation — deterministic per region, never per request."""

import hashlib
from typing import TYPE_CHECKING

from app.models import Region

if TYPE_CHECKING:
    from app.config import Settings

_ACCEPT_LANGUAGE = "ru-RU"
_ACCEPT_ENCODING = "gzip, deflate"  # no brotli — requests won't decode it
_WB_ORIGIN = "https://www.wildberries.ru"
_WB_REFERER = "https://www.wildberries.ru/"

# Each identity: (User-Agent, sec-ch-ua, sec-ch-ua-platform). Index 0 preserves today's default.
_WB_IDENTITIES: tuple[tuple[str, str, str], ...] = (
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        '"Chromium";v="126", "Google Chrome";v="126", "Not.A/Brand";v="24"',
        '"Windows"',
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        '"Chromium";v="126", "Google Chrome";v="126", "Not.A/Brand";v="24"',
        '"macOS"',
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        '"Chromium";v="126", "Google Chrome";v="126", "Not.A/Brand";v="24"',
        '"Linux"',
    ),
)

# Preserve `settings.ozon_impersonate` ("chrome") as the default identity at index 0.
_OZON_IMPERSONATE_TARGETS: tuple[str, ...] = ("chrome", "chrome124", "chrome120")


def _region_index(region_code: str, choices: int) -> int:
    """Stable hash of the region code → index into an allowed-identity list."""
    digest = hashlib.sha256(region_code.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % choices


def wb_headers(region: Region) -> dict[str, str]:
    """WB request headers, with a UA/sec-ch-ua identity chosen deterministically per region."""
    ua, sec_ch_ua, sec_ch_ua_platform = _WB_IDENTITIES[_region_index(region.code, len(_WB_IDENTITIES))]
    return {
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": _ACCEPT_LANGUAGE,
        "Accept-Encoding": _ACCEPT_ENCODING,
        "Origin": _WB_ORIGIN,
        "Referer": _WB_REFERER,
        "sec-ch-ua": sec_ch_ua,
        "sec-ch-ua-platform": sec_ch_ua_platform,
    }


def ozon_impersonate(region: Region, settings: "Settings") -> str:
    """Pick a `curl_cffi` impersonate target deterministically per region.

    `settings.ozon_impersonate` stays the fallback for the default identity so
    committed-sample parser tests and existing behaviour are unaffected.
    """
    targets = (
        _OZON_IMPERSONATE_TARGETS if settings.ozon_impersonate == "chrome" else (settings.ozon_impersonate,)
    )
    return targets[_region_index(region.code, len(targets))]
