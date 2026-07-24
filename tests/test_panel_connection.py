"""app.panel — «Параметры подключения» tab: renders io.json, POST persists, preview validates (ADR-0014)."""

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.panel import app as panel_app


def _client() -> TestClient:
    return TestClient(panel_app.create_app())


def _settings(tmp_path):
    return Settings(io_config_path=str(tmp_path / "io.json"))


def test_connection_tab_renders_empty_form_when_no_io_json(tmp_path) -> None:
    settings = _settings(tmp_path)
    with patch("app.panel.app.get_settings", return_value=settings):
        response = _client().get("/tab/connection")

    assert response.status_code == 200
    assert "Параметры подключения" in response.text


def test_connection_tab_prefills_from_io_json(tmp_path) -> None:
    io_path = tmp_path / "io.json"
    io_path.write_text(
        json.dumps(
            {
                "source": {
                    "kind": "csv",
                    "products_path": "data/products.csv",
                    "mapping": {"products": {"sku": "SKU"}},
                }
            }
        )
    )
    settings = _settings(tmp_path)

    with patch("app.panel.app.get_settings", return_value=settings):
        response = _client().get("/tab/connection")

    assert response.status_code == 200
    assert "data/products.csv" in response.text
    assert "5.1 Источник" in response.text
    assert "5.2 Маппинг входа" in response.text
    assert "5.3 Приёмник" in response.text
    assert "5.4 Маппинг выхода" in response.text


def test_post_connection_source_persists(tmp_path) -> None:
    settings = _settings(tmp_path)

    with patch("app.panel.app.get_settings", return_value=settings):
        response = _client().post(
            "/connection/source",
            data={
                "kind": "csv",
                "products_path": "products.csv",
                "regions_path": "",
                "map_products__marketplace": "Площадка",
                "map_products__sku": "Артикул",
                "map_products__url": "Ссылка",
                "map_products__name": "Название",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    saved = json.loads((tmp_path / "io.json").read_text())
    assert saved["source"]["kind"] == "csv"
    assert saved["source"]["products_path"] == "products.csv"
    assert saved["source"]["mapping"]["products"]["sku"] == "Артикул"


def test_post_connection_sink_persists(tmp_path) -> None:
    settings = _settings(tmp_path)

    with patch("app.panel.app.get_settings", return_value=settings):
        response = _client().post(
            "/connection/sink",
            data={
                "kind": "csv",
                "path": "out.csv",
                "map_results__sku": "SKU",
                "map_results__region": "Region",
                "map_results__price": "Price",
                "map_results__measured_at": "MeasuredAt",
                "map_results__status": "Status",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    saved = json.loads((tmp_path / "io.json").read_text())
    assert saved["sink"]["kind"] == "csv"
    assert saved["sink"]["path"] == "out.csv"
    assert saved["sink"]["mapping"]["results"]["sku"] == "SKU"


def test_preview_source_returns_mapped_rows(tmp_path) -> None:
    products_path = tmp_path / "products.csv"
    products_path.write_text("Площадка,Артикул,Ссылка,Название\nwb,1,https://x/1,Товар А\n", encoding="utf-8")
    settings = _settings(tmp_path)

    with patch("app.panel.app.get_settings", return_value=settings):
        response = _client().post(
            "/connection/preview",
            data={
                "target": "source",
                "kind": "csv",
                "products_path": str(products_path),
                "map_products__marketplace": "Площадка",
                "map_products__sku": "Артикул",
                "map_products__url": "Ссылка",
                "map_products__name": "Название",
            },
        )

    assert response.status_code == 200
    assert "Товар А" in response.text


def test_preview_reports_shifted_mapping_as_error(tmp_path) -> None:
    products_path = tmp_path / "products.csv"
    products_path.write_text("marketplace,sku,url,name\nwb,1,https://x/1,A\n", encoding="utf-8")
    settings = _settings(tmp_path)

    with patch("app.panel.app.get_settings", return_value=settings):
        response = _client().post(
            "/connection/preview",
            data={
                "target": "source",
                "kind": "csv",
                "products_path": str(products_path),
                "map_products__marketplace": "marketplace",
                "map_products__sku": "sku",
                "map_products__url": "url",
                "map_products__name": "shifted_column",
            },
        )

    assert response.status_code == 200
    assert "absent from source header" in response.text
