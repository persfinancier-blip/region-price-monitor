from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_ozon_reference_entrypoint.py"
PROMPT = ROOT / "prompts" / "work" / "G01-SG04" / "PR01-ST01-T01-C15.I01.md"
RUNNER = ROOT / "tests" / "RUN_OZON_REFERENCE_ENTRYPOINT_C15.bat"


class OzonReferenceEntrypointC15Tests(unittest.TestCase):
    def test_files_exist(self):
        self.assertTrue(PROBE.exists())
        self.assertTrue(PROMPT.exists())
        self.assertTrue(RUNNER.exists())

    def test_probe_uses_direct_reference_entrypoint(self):
        src = PROBE.read_text(encoding="utf-8")
        self.assertIn("/api/entrypoint-api.bx/page/json/v2", src)
        self.assertIn('(\"chrome\", \"chrome146\", \"chrome145\", \"chrome142\", \"chrome136\")', src)
        self.assertIn('"x-o3-app-name": "dweb_client"', src)
        self.assertNotIn('curl_request_via_proxy(context, "GET", "https://www.ozon.ru/"', src)
        self.assertNotIn('curl_request_via_proxy(context, "GET", f"https://www.ozon.ru/product/', src)

    def test_probe_binds_price_semantically(self):
        src = PROBE.read_text(encoding="utf-8")
        self.assertIn('block.get("component") != component_name', src)
        self.assertIn('state_id = block.get("stateId")', src)
        self.assertIn('"ambiguous_price_widgets"', src)
        self.assertIn('"wrong_product_page"', src)
        self.assertIn('OZON_REFERENCE_ENTRYPOINT_DATA_ACCESS_PROVEN', src)

    def test_probe_keeps_proxycontext_authority(self):
        src = PROBE.read_text(encoding="utf-8")
        self.assertIn("ProxyContext.from_city", src)
        self.assertIn("curl_request_via_proxy", src)
        self.assertNotIn('normalize_proxy(', src)


if __name__ == "__main__":
    unittest.main()
