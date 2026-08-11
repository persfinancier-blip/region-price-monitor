from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import pandas as pd

import db as db_module
from city_sources import load_cities_file
from input_models import (
    CityRecord,
    InputValidationError,
    normalize_city_record,
    normalize_product_mapping,
    normalize_product_rows,
)
from inputs import InputSourceError, load_input_bundle
from product_sources import load_products_file, load_products_json
from transport import ProxyContext, ProxyContextError, TransportKind, TransportOutcome


class _FakeCursor:
    def __init__(self, rows=None, executed=None):
        self.rows = list(rows or [])
        self.executed = executed if executed is not None else []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(str(sql).split()), params))

    def fetchall(self):
        return list(self.rows)


class _FakeConnection:
    def __init__(self, rows=None, executed=None):
        self.rows = rows or []
        self.executed = executed if executed is not None else []

    def cursor(self, cursor_factory=None):
        return _FakeCursor(self.rows, self.executed)


class _FakeBundleDB:
    def __init__(self, products, cities):
        self.products = products
        self.cities = cities

    def load_skus(self, active_only=True):
        return self.products

    def load_cities(self):
        return self.cities


class Wave1ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_product_rows_and_json_normalize_to_canonical_productset(self):
        rows = [
            {"marketplace": " WB ", "sku": 123.0},
            {"marketplace": "ozon", "sku": " 456 "},
        ]
        expected = {"wb": ["123"], "ozon": ["456"]}
        self.assertEqual(normalize_product_rows(rows), expected)

        path = self.root / "products.json"
        path.write_text(json.dumps({"wb": [123], "ozon": ["456"]}), encoding="utf-8")
        self.assertEqual(load_products_json(path), expected)

    def test_product_invalid_marketplace_fails_explicitly(self):
        with self.assertRaises(InputValidationError) as ctx:
            normalize_product_rows([{"marketplace": "market-x", "sku": "1"}])
        self.assertIn("unsupported marketplace", str(ctx.exception))

    def test_product_csv_excel_semantic_parity(self):
        frame = pd.DataFrame([
            {"marketplace": "wb", "sku": 101},
            {"marketplace": "ozon", "sku": 202},
        ])
        csv_path = self.root / "products.csv"
        xlsx_path = self.root / "products.xlsx"
        frame.to_csv(csv_path, index=False)
        frame.to_excel(xlsx_path, index=False)
        self.assertEqual(load_products_file(csv_path), load_products_file(xlsx_path))
        self.assertEqual(load_products_file(csv_path), {"wb": ["101"], "ozon": ["202"]})

    def test_parserdb_load_skus_uses_canonical_normalizer(self):
        parser_db = db_module.ParserDB.__new__(db_module.ParserDB)
        rows = [{"sku": 101, "marketplace": "WB"}, {"sku": "202", "marketplace": "ozon"}]

        @contextmanager
        def fake_connect():
            yield _FakeConnection(rows=rows)

        parser_db._connect = fake_connect
        self.assertEqual(parser_db.load_skus(), {"wb": ["101"], "ozon": ["202"]})

    def test_cityrecord_exact_minimum_and_optional_dest(self):
        record = normalize_city_record({
            "city": " Moscow ",
            "proxy": "proxy.example:8080",
            "proxy_user": "demo-user",
            "proxy_password": "demo-pass",
        })
        self.assertEqual(
            record,
            CityRecord("Moscow", "proxy.example:8080", "demo-user", "demo-pass", None),
        )
        self.assertNotIn("demo-pass", repr(record))
        self.assertNotIn("demo-user", repr(record))

    def test_each_required_city_field_missing_or_blank_fails(self):
        base = {
            "city": "Moscow",
            "proxy": "proxy.example:8080",
            "proxy_user": "user",
            "proxy_password": "pass",
        }
        for field in ("city", "proxy", "proxy_user", "proxy_password"):
            for mode in ("missing", "blank"):
                with self.subTest(field=field, mode=mode):
                    raw = dict(base)
                    if mode == "missing":
                        raw.pop(field)
                    else:
                        raw[field] = "   "
                    with self.assertRaises(InputValidationError) as ctx:
                        normalize_city_record(raw)
                    self.assertIn(field, str(ctx.exception))

    def test_city_csv_excel_parity_and_numeric_wb_dest(self):
        frame = pd.DataFrame([
            {
                "city": "Moscow",
                "proxy": "proxy1.example:8080",
                "proxy_user": "u1",
                "proxy_password": "p1",
                "wb_dest": 123,
            },
            {
                "city": "Kazan",
                "proxy": "proxy2.example:8080",
                "proxy_user": "u2",
                "proxy_password": "p2",
                "wb_dest": None,
            },
        ])
        csv_path = self.root / "cities.csv"
        xlsx_path = self.root / "cities.xlsx"
        frame.to_csv(csv_path, index=False)
        frame.to_excel(xlsx_path, index=False)
        csv_records = load_cities_file(csv_path)
        xlsx_records = load_cities_file(xlsx_path)
        self.assertEqual(csv_records, xlsx_records)
        self.assertEqual(csv_records[0].wb_dest, "123")
        self.assertIsNone(csv_records[1].wb_dest)

    def test_city_file_invalid_row_is_not_silently_dropped(self):
        path = self.root / "cities.csv"
        path.write_text(
            "city,proxy,proxy_user,proxy_password,wb_dest\n"
            "Moscow,proxy.example:8080,user,,\n",
            encoding="utf-8",
        )
        with self.assertRaises(InputValidationError) as ctx:
            load_cities_file(path)
        self.assertIn("proxy_password", str(ctx.exception))
        self.assertIn("row 1", str(ctx.exception))

    def test_parserdb_schema_contains_only_minimum_city_user_fields_and_loads(self):
        parser_db = db_module.ParserDB.__new__(db_module.ParserDB)
        executed = []

        @contextmanager
        def schema_connect():
            yield _FakeConnection(executed=executed)

        parser_db._connect = schema_connect
        parser_db._ensure_tables()
        ddl = "\n".join(sql for sql, _ in executed)
        self.assertIn("CREATE TABLE IF NOT EXISTS parser_cities", ddl)
        for field in ("city", "proxy", "proxy_user", "proxy_password", "wb_dest"):
            self.assertIn(field, ddl)
        for forbidden in ("proxy_id", "provider", "rotation_url", "session_id"):
            self.assertNotIn(forbidden, ddl)

        rows = [{
            "city": "Moscow",
            "proxy": "proxy.example:8080",
            "proxy_user": "u",
            "proxy_password": "p",
            "wb_dest": None,
        }]

        @contextmanager
        def load_connect():
            yield _FakeConnection(rows=rows)

        parser_db._connect = load_connect
        self.assertEqual(parser_db.load_cities(), [CityRecord("Moscow", "proxy.example:8080", "u", "p", None)])

    def test_parserdb_invalid_city_row_fails_explicitly(self):
        parser_db = db_module.ParserDB.__new__(db_module.ParserDB)
        rows = [{
            "city": "Moscow",
            "proxy": "",
            "proxy_user": "u",
            "proxy_password": "p",
            "wb_dest": None,
        }]

        @contextmanager
        def fake_connect():
            yield _FakeConnection(rows=rows)

        parser_db._connect = fake_connect
        with self.assertRaises(InputValidationError) as ctx:
            parser_db.load_cities()
        self.assertIn("proxy", str(ctx.exception))

    def test_all_four_product_city_source_combinations_share_one_shape(self):
        product_frame = pd.DataFrame([
            {"marketplace": "wb", "sku": 101},
            {"marketplace": "ozon", "sku": 202},
        ])
        city_frame = pd.DataFrame([
            {
                "city": "Moscow",
                "proxy": "proxy.example:8080",
                "proxy_user": "u",
                "proxy_password": "p",
                "wb_dest": None,
            }
        ])
        product_file = self.root / "products.csv"
        city_file = self.root / "cities.csv"
        product_frame.to_csv(product_file, index=False)
        city_frame.to_csv(city_file, index=False)
        db = _FakeBundleDB(
            {"wb": [101], "ozon": ["202"]},
            [{
                "city": "Moscow",
                "proxy": "proxy.example:8080",
                "proxy_user": "u",
                "proxy_password": "p",
                "wb_dest": None,
            }],
        )
        bundles = [
            load_input_bundle(product_source="file", city_source="file", product_file=product_file, city_file=city_file),
            load_input_bundle(product_source="file", city_source="db", product_file=product_file, db=db),
            load_input_bundle(product_source="db", city_source="file", city_file=city_file, db=db),
            load_input_bundle(product_source="db", city_source="db", db=db),
        ]
        for bundle in bundles[1:]:
            self.assertEqual(bundle, bundles[0])
        self.assertEqual(set(bundles[0]), {"products", "cities"})

    def test_empty_sources_fail_instead_of_masquerading_as_valid_bundle(self):
        db = _FakeBundleDB({"wb": [], "ozon": []}, [{
            "city": "Moscow",
            "proxy": "proxy.example:8080",
            "proxy_user": "u",
            "proxy_password": "p",
            "wb_dest": None,
        }])
        with self.assertRaises(InputSourceError):
            load_input_bundle(product_source="db", city_source="db", db=db)

    def test_new_cityset_handoff_does_not_use_legacy_region_preparation(self):
        source = (CORE / "inputs.py").read_text(encoding="utf-8")
        for forbidden in ("review_profiles", "repair_regions", "add_new_regions", "warm_browser"):
            self.assertNotIn(forbidden, source)

    def test_proxy_context_default_scheme_reserved_credentials_and_safe_repr(self):
        record = CityRecord(
            "Moscow",
            "proxy.example:8080",
            "user@corp",
            "p:a/ss% word",
            None,
        )
        context = ProxyContext.from_city(record)
        self.assertEqual(context.scheme, "http")
        self.assertEqual(
            context.endpoint,
            "http://user%40corp:p%3Aa%2Fss%25%20word@proxy.example:8080",
        )
        self.assertEqual(context.safe_identity, "Moscow@http://proxy.example:8080")
        self.assertNotIn("user@corp", repr(context))
        self.assertNotIn("p:a/ss", repr(context))
        self.assertEqual(context.requests_proxies()["http"], context.endpoint)
        self.assertEqual(context.requests_proxies()["https"], context.endpoint)

    def test_proxy_context_preserves_supported_scheme_and_needs_no_wb_dest(self):
        context = ProxyContext.from_city({
            "city": "Kazan",
            "proxy": "socks5://proxy.example:1080",
            "proxy_user": "u",
            "proxy_password": "p",
        })
        self.assertEqual(context.scheme, "socks5")
        self.assertEqual(context.city, "Kazan")

    def test_proxy_context_rejects_malformed_or_credential_bearing_proxy_address(self):
        base = {
            "city": "Moscow",
            "proxy_user": "u",
            "proxy_password": "p",
        }
        for proxy in ("proxy.example", "ftp://proxy.example:21", "http://x:y@proxy.example:8080", "http://:8080"):
            with self.subTest(proxy=proxy):
                with self.assertRaises((ProxyContextError, InputValidationError)):
                    ProxyContext.from_city({**base, "proxy": proxy})

    def test_transport_http_outcomes_are_typed_and_not_fake_empty_data(self):
        ok = TransportOutcome.from_http(200, body="{}")
        self.assertTrue(ok.ok)
        self.assertEqual(ok.kind, TransportKind.SUCCESS)
        self.assertEqual(ok.body, "{}")

        auth = TransportOutcome.from_http(407, body="proxy denied")
        self.assertFalse(auth.ok)
        self.assertEqual(auth.kind, TransportKind.PROXY_AUTH_ERROR)

        http = TransportOutcome.from_http(503, body="down")
        self.assertEqual(http.kind, TransportKind.HTTP_ERROR)
        self.assertIsNotNone(http.body)

    def test_transport_exception_categories_and_secret_redaction(self):
        context = ProxyContext.from_city({
            "city": "Moscow",
            "proxy": "proxy.example:8080",
            "proxy_user": "secret-user",
            "proxy_password": "secret-pass",
        })
        cases = [
            (RuntimeError("proxy authentication 407 secret-pass"), TransportKind.PROXY_AUTH_ERROR),
            (RuntimeError("proxy connection failed secret-user"), TransportKind.PROXY_CONNECTION_ERROR),
            (TimeoutError("timed out"), TransportKind.TIMEOUT),
            (ConnectionError("TLS connection failed"), TransportKind.CONNECTION_ERROR),
            (ValueError("unexpected"), TransportKind.UNEXPECTED_ERROR),
        ]
        for exc, expected in cases:
            with self.subTest(expected=expected):
                outcome = TransportOutcome.from_exception(exc, context=context)
                self.assertEqual(outcome.kind, expected)
                self.assertNotIn("secret-user", outcome.message or "")
                self.assertNotIn("secret-pass", outcome.message or "")

    def test_transport_safe_dict_never_exposes_body(self):
        outcome = TransportOutcome.from_http(500, body="possibly sensitive marketplace body", message="HTTP 500")
        safe = outcome.safe_dict()
        self.assertNotIn("body", safe)
        self.assertEqual(safe["kind"], "http_error")


if __name__ == "__main__":
    unittest.main()
