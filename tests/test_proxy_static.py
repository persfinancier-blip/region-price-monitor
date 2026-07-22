"""Unit tests for StaticProxyProvider — no network, always runs in CI."""

import pytest

from app.proxy.static import StaticProxyProvider, make_proxy_provider, parse_proxy_map


class _Settings:
    def __init__(self, proxy_provider: str, proxy_url: str | None, proxy_map_json: str | None) -> None:
        self.proxy_provider = proxy_provider
        self.proxy_url = proxy_url
        self.proxy_map_json = proxy_map_json


async def test_acquire_region_in_map_returns_its_proxy_url() -> None:
    provider = StaticProxyProvider({"msk": "http://user:pass@msk-proxy.example.com:8080"})

    lease = await provider.acquire("msk")

    assert lease.proxy_url == "http://user:pass@msk-proxy.example.com:8080"
    assert lease.region_code == "msk"
    assert "user" not in lease.ref
    assert "pass" not in lease.ref
    assert "msk-proxy.example.com" in lease.ref


async def test_acquire_unknown_region_falls_back_to_global_proxy() -> None:
    provider = StaticProxyProvider(
        {"msk": "http://msk-proxy.example.com:8080"}, "http://fallback.example.com:9090"
    )

    lease = await provider.acquire("spb")

    assert lease.proxy_url == "http://fallback.example.com:9090"


async def test_acquire_unknown_region_no_fallback_is_direct() -> None:
    provider = StaticProxyProvider({"msk": "http://msk-proxy.example.com:8080"})

    lease = await provider.acquire("spb")

    assert lease.proxy_url is None
    assert lease.ref.endswith(":direct")


def test_parse_proxy_map_invalid_json_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="invalid proxy_map_json"):
        parse_proxy_map("{not valid json")


def test_parse_proxy_map_non_object_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="proxy_map_json must be"):
        parse_proxy_map("[1, 2, 3]")


def test_parse_proxy_map_empty_returns_empty_dict() -> None:
    assert parse_proxy_map(None) == {}
    assert parse_proxy_map("") == {}


def test_make_proxy_provider_static_builds_from_settings() -> None:
    settings = _Settings("static", None, '{"msk": "http://msk-proxy.example.com:8080"}')

    provider = make_proxy_provider(settings)

    assert isinstance(provider, StaticProxyProvider)


def test_make_proxy_provider_unknown_provider_raises_clear_error() -> None:
    settings = _Settings("commercial", None, None)

    with pytest.raises(ValueError, match="unknown proxy_provider"):
        make_proxy_provider(settings)
