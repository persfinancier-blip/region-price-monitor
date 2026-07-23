"""wb_headers / ozon_impersonate — deterministic per region, no network/DB."""

from app.collectors.fingerprint import _OZON_IMPERSONATE_TARGETS, _WB_IDENTITIES, ozon_impersonate, wb_headers
from app.config import Settings
from app.models import Region

_MSK = Region(code="msk", name="Moscow", geo={})
_SPB = Region(code="spb", name="Saint Petersburg", geo={})


def test_wb_headers_deterministic_same_region() -> None:
    first = wb_headers(_MSK)
    second = wb_headers(_MSK)
    assert first == second


def test_wb_headers_default_identity_in_allowed_set() -> None:
    headers = wb_headers(_MSK)
    allowed_uas = {identity[0] for identity in _WB_IDENTITIES}
    assert headers["User-Agent"] in allowed_uas


def test_wb_headers_may_differ_across_regions() -> None:
    regions = [Region(code=f"region-{i}", name="R", geo={}) for i in range(10)]
    uas = {wb_headers(r)["User-Agent"] for r in regions}
    assert len(uas) > 1


def test_ozon_impersonate_deterministic_same_region() -> None:
    settings = Settings()
    first = ozon_impersonate(_MSK, settings)
    second = ozon_impersonate(_MSK, settings)
    assert first == second


def test_ozon_impersonate_default_within_allowed_set() -> None:
    settings = Settings()
    assert ozon_impersonate(_MSK, settings) in _OZON_IMPERSONATE_TARGETS


def test_ozon_impersonate_non_chrome_setting_is_pass_through() -> None:
    settings = Settings(ozon_impersonate="firefox135")
    assert ozon_impersonate(_MSK, settings) == "firefox135"
    assert ozon_impersonate(_SPB, settings) == "firefox135"
