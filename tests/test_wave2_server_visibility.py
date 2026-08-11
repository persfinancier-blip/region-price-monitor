from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_server_visibility.py"
RUNNER = ROOT / "tests" / "RUN_WAVE2_LIVE_PROBES.bat"


class ServerVisibilityContractTests(unittest.TestCase):
    def test_probe_uses_server_transports_without_browser_runtime(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("from requests_transport import request_via_proxy as requests_request", source)
        self.assertIn("from curl_transport import request_via_proxy as curl_request", source)
        self.assertNotIn("selenium", source.lower())
        self.assertNotIn("undetected_chromedriver", source)
        self.assertNotIn("playwright", source.lower())

    def test_probe_targets_only_official_product_pages_not_data_endpoints(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("https://www.wildberries.ru/catalog/{wb_sku}/detail.aspx", source)
        self.assertIn("https://www.ozon.ru/product/{ozon_sku}/", source)
        self.assertNotIn("card.wb.ru", source)
        self.assertNotIn("composer-api", source)
        self.assertNotIn("state-webPrice", source)

    def test_gate_treats_http_antibot_as_reachability_not_data_success(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn('"OZON_SITE_REACHABLE_ANTIBOT_RESPONSE"', source)
        self.assertIn('"SERVER_SEES_WB_AND_OZON"', source)
        self.assertIn("outcome.status_code is not None", source)

    def test_live_runner_calls_server_visibility_probe(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("tools\\probe_server_visibility.py", source)
        self.assertIn("SERVER_SEES_WB_AND_OZON", source)
        self.assertNotIn("probe_browser_visibility.py", source)


if __name__ == "__main__":
    unittest.main()
