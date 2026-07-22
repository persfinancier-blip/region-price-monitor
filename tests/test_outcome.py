"""Unit tests for classify_outcome — pure, no network, always runs in CI."""

import requests
from curl_cffi.requests.exceptions import Timeout as CurlTimeout

from app.collectors.outcome import classify_outcome
from app.enums import Outcome


def test_200_with_products_is_ok() -> None:
    assert classify_outcome(status_code=200, exc=None, empty_products=False) == Outcome.OK


def test_403_is_hard_ban() -> None:
    assert classify_outcome(status_code=403, exc=ValueError("blocked")) == Outcome.HARD_BAN


def test_429_is_hard_ban() -> None:
    assert classify_outcome(status_code=429, exc=ValueError("rate limited")) == Outcome.HARD_BAN


def test_timeout_exception_is_timeout() -> None:
    assert classify_outcome(status_code=None, exc=requests.Timeout("timed out")) == Outcome.TIMEOUT


def test_other_transport_error_is_error() -> None:
    assert classify_outcome(status_code=None, exc=requests.ConnectionError("refused")) == Outcome.ERROR


def test_200_with_empty_products_is_soft_ban() -> None:
    assert classify_outcome(status_code=200, exc=ValueError("empty"), empty_products=True) == Outcome.SOFT_BAN


def test_ozon_200_is_ok() -> None:
    assert classify_outcome(status_code=200, exc=None) == Outcome.OK


def test_ozon_403_is_hard_ban() -> None:
    assert classify_outcome(status_code=403, exc=ValueError("blocked")) == Outcome.HARD_BAN


def test_ozon_anti_bot_signal_is_hard_ban() -> None:
    assert classify_outcome(status_code=200, exc=ValueError("captcha"), anti_bot=True) == Outcome.HARD_BAN


def test_ozon_curl_cffi_timeout_is_timeout() -> None:
    assert classify_outcome(status_code=None, exc=CurlTimeout("timed out")) == Outcome.TIMEOUT


def test_ozon_transport_error_is_error() -> None:
    assert classify_outcome(status_code=None, exc=ConnectionError("refused")) == Outcome.ERROR
