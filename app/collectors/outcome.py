"""Pure classification of a collection attempt into an Outcome (no network)."""

import requests
from curl_cffi.requests.exceptions import Timeout as CurlTimeout

from app.enums import Outcome

_BAN_STATUS_CODES = {403, 429}


def classify_outcome(
    *,
    status_code: int | None,
    exc: Exception | None,
    empty_products: bool = False,
    anti_bot: bool = False,
) -> Outcome:
    """Classify a completed/failed collection attempt.

    - HTTP 200 with no exception and non-empty parsed products → OK.
    - HTTP 200 with an empty `products` list, or a valid-but-suspicious body
      (`anti_bot`, e.g. Ozon captcha page) → SOFT_BAN.
    - HTTP 403/429, or an explicit `anti_bot` signal → HARD_BAN (anti-bot / rate limiting).
    - `requests.Timeout` / `curl_cffi` `Timeout` → TIMEOUT.
    - Any other exception (network/transport/parse) → ERROR.
    """
    if isinstance(exc, requests.Timeout | CurlTimeout):
        return Outcome.TIMEOUT
    if status_code in _BAN_STATUS_CODES or anti_bot:
        return Outcome.HARD_BAN
    if status_code == 200 and empty_products:
        return Outcome.SOFT_BAN
    if exc is not None:
        return Outcome.ERROR
    if status_code == 200:
        return Outcome.OK
    return Outcome.ERROR
