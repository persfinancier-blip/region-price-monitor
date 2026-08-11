from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_ozon_single_proxy_access.py"
RUNNER = ROOT / "tests" / "RUN_OZON_SINGLE_ACCESS_PROBE.bat"
PROMPT = ROOT / "prompts" / "work" / "G01-SG04" / "PR01-ST01-T01-C11.I01.md"


class OzonSingleProxyAccessTests(unittest.TestCase):
    def test_probe_requires_only_one_proxy_context(self):
        source = PROBE.read_text(encoding="utf-8").lower()
        self.assertEqual(source.count("_make_context()"), 2)  # definition + one invocation
        self.assertNotIn("context_b", source)
        self.assertNotIn("city b", source)
        self.assertNotIn("sync_playwright(", source)
        self.assertNotIn("chromium.launch(", source)

    def test_probe_checks_product_page_and_exact_entrypoint(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn('product_url = f"https://www.ozon.ru/product/{sku}/"', source)
        self.assertIn('API_URL = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"', source)
        self.assertIn('params={"url": f"/product/{sku}/"}', source)
        self.assertIn("OZON_SINGLE_PROXY_ENTRYPOINT_DATA_ACCESS_PROVEN", source)

    def test_data_access_requires_http_200_json_and_sku_binding(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("api.status_code == 200 and payload is not None and exact_sku_bound", source)
        self.assertIn("sku in page_info_url", source)
        prompt = PROMPT.read_text(encoding="utf-8")
        self.assertIn("HTTP 200 + decodable JSON", prompt)
        self.assertIn("no second city/proxy", prompt.lower())

    def test_runner_targets_only_single_proxy_probe(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("probe_ozon_single_proxy_access.py", source)
        self.assertNotIn("probe_ozon_proxy_region_effect.py", source)


if __name__ == "__main__":
    unittest.main()
