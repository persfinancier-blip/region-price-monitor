"""Pure classification of a collection attempt into an Outcome (no network)."""

import requests

from app.enums import Outcome

_BAN_STATUS_CODES = {403, 429}


def classify_outcome(
    *,
    status_code: int | None,
    exc: Exception | None,
    empty_products: bool = False,
) -> Outcome:
    """Classify a completed/failed collection attempt.

    - HTTP 200 with no exception and non-empty parsed products → OK.
    - HTTP 200 with an empty `products` list (valid response, suspicious body) → SOFT_BAN.
    - HTTP 403/429 → HARD_BAN (WB anti-bot / rate limiting).
    - `requests.Timeout` → TIMEOUT.
    - Any other exception (network/transport/parse) → ERROR.
    """
    if isinstance(exc, requests.Timeout):
        return Outcome.TIMEOUT
    if status_code in _BAN_STATUS_CODES:
        return Outcome.HARD_BAN
    if status_code == 200 and empty_products:
        return Outcome.SOFT_BAN
    if exc is not None:
        return Outcome.ERROR
    if status_code == 200:
        return Outcome.OK
    return Outcome.ERROR
