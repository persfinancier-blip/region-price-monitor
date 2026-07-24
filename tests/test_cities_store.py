"""app.scripts.cities — local settings store: load/save, effective resolution, CRUD, seed."""

from contextlib import asynccontextmanager

from app.config import Settings
from app.scripts import cities


class _FakeRegion:
    def __init__(self, code: str, name: str, geo: dict) -> None:
        self.code = code
        self.name = name
        self.geo = geo


class _FakeRegionRepo:
    def __init__(self, regions: list[_FakeRegion]) -> None:
        self._regions = regions

    async def list_active(self):
        return self._regions


class _FakeStorage:
    def __init__(self, regions: list[_FakeRegion]) -> None:
        self.regions = _FakeRegionRepo(regions)


def _fake_storage_factory(regions: list[_FakeRegion]):
    @asynccontextmanager
    async def factory():
        yield _FakeStorage(regions)

    return factory


def _config() -> cities.CitiesConfig:
    return cities.CitiesConfig(
        defaults={
            "wb": cities.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
            "ozon": cities.MarketplaceDefaults(enabled=True, proxy=None, interval_min=360),
        },
        cities=[],
    )


def test_save_writes_file_atomically(tmp_path) -> None:
    settings = Settings(city_config_path=str(tmp_path / "cities.json"))
    config = cities.add_city(_config(), code="msk", name="Москва")

    cities.save(config, settings)

    assert (tmp_path / "cities.json").exists()
    assert not (tmp_path / "cities.json.tmp").exists()


async def test_load_round_trip(tmp_path) -> None:
    settings = Settings(city_config_path=str(tmp_path / "cities.json"))
    config = cities.add_city(_config(), code="msk", name="Москва")
    config = cities.set_marketplace(
        config,
        code="msk",
        marketplace="ozon",
        mode="override",
        enabled=True,
        proxy="http://p",
        interval_min=90,
    )
    cities.save(config, settings)

    loaded = await cities.load(settings)

    assert loaded.cities[0].code == "msk"
    assert loaded.cities[0].ozon.mode == "override"
    assert loaded.cities[0].ozon.proxy == "http://p"
    assert loaded.cities[0].ozon.interval_min == 90


def test_list_effective_resolves_inherit_and_override_and_drops_disabled() -> None:
    config = _config()
    config = cities.add_city(config, code="msk", name="Москва")
    config = cities.add_city(config, code="spb", name="СПб")
    config = cities.set_marketplace(
        config,
        code="msk",
        marketplace="ozon",
        mode="override",
        enabled=True,
        proxy="http://p",
        interval_min=90,
    )
    config = cities.set_marketplace(
        config, code="spb", marketplace="wb", mode="override", enabled=False, proxy=None, interval_min=360
    )

    effective = {c.code: c for c in cities.list_effective(config)}

    msk = effective["msk"]
    assert msk.marketplaces["wb"].mode == "inherit"
    assert msk.marketplaces["wb"].interval_min == 360
    assert msk.marketplaces["ozon"].mode == "override"
    assert msk.marketplaces["ozon"].proxy == "http://p"
    assert msk.marketplaces["ozon"].interval_min == 90

    spb = effective["spb"]
    assert "wb" not in spb.marketplaces  # disabled -> dropped entirely
    assert "ozon" in spb.marketplaces  # still inherits


def test_add_city_is_idempotent_on_existing_code() -> None:
    config = cities.add_city(_config(), code="msk", name="Москва")
    config2 = cities.add_city(config, code="msk", name="Duplicate")

    assert len(config2.cities) == 1
    assert config2.cities[0].name == "Москва"


def test_set_enabled_toggles_and_switches_to_override() -> None:
    config = cities.add_city(_config(), code="msk", name="Москва")

    config = cities.set_enabled(config, code="msk", marketplace="wb", enabled=False)

    city = config.cities[0]
    assert city.wb.mode == "override"
    assert city.wb.enabled is False

    effective = cities.list_effective(config)[0]
    assert "wb" not in effective.marketplaces


def test_set_marketplace_keep_proxy_if_empty() -> None:
    config = cities.add_city(_config(), code="msk", name="Москва")
    config = cities.set_marketplace(
        config,
        code="msk",
        marketplace="wb",
        mode="override",
        enabled=True,
        proxy="http://real",
        interval_min=100,
    )

    config = cities.set_marketplace(
        config,
        code="msk",
        marketplace="wb",
        mode="override",
        enabled=True,
        proxy=None,
        interval_min=100,
        keep_proxy_if_empty=True,
    )

    assert config.cities[0].wb.proxy == "http://real"


def test_remove_city_drops_from_config() -> None:
    config = cities.add_city(_config(), code="msk", name="Москва")

    config = cities.remove_city(config, code="msk")

    assert config.cities == []


async def test_seed_from_regions_when_file_absent(tmp_path) -> None:
    settings = Settings(city_config_path=str(tmp_path / "no-such-file.json"))
    regions = [
        _FakeRegion("msk", "Москва", geo={"ozon": "Moscow"}),
        _FakeRegion("spb", "СПб", geo={}),  # no ozon geo
    ]
    storage_factory = _fake_storage_factory(regions)

    config = await cities.load(settings, storage_factory)

    effective = {c.code: c for c in cities.list_effective(config)}
    assert "wb" in effective["msk"].marketplaces
    assert "ozon" in effective["msk"].marketplaces
    assert "wb" in effective["spb"].marketplaces
    assert "ozon" not in effective["spb"].marketplaces  # no ozon geo -> disabled


def test_format_report_masks_proxy() -> None:
    config = cities.add_city(_config(), code="msk", name="Москва")
    config = cities.set_marketplace(
        config,
        code="msk",
        marketplace="wb",
        mode="override",
        enabled=True,
        proxy="http://user:pass@proxy.example",
        interval_min=90,
    )

    report = cities.format_report(config)

    assert "user:pass" not in report
    assert "***" in report


def test_main_help_smoke() -> None:
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        cities.main(["--help"])
    assert exc_info.value.code == 0
