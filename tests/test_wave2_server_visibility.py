from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_server_visibility.py"
RUNNER = ROOT / "tests" / "RUN_WAVE2_LIVE_PROBES.bat"


class ServerVisibilityContractTests(unittest.TestCase):
    def test_probe_uses_server_transports_without_browser_runtime(self):
        source = PROBE.read_text(encoding="utf-8")
        low = source.lower()
        self.assertIn("from requests_transport import request_via_proxy as requests_request", source)
        self.assertIn("from curl_transport import request_via_proxy as curl_request", source)
        # Human-readable diagnostics may mention browser tools; only actual runtime imports/usages are forbidden.
        self.assertNotIn("import selenium", low)
        self.assertNotIn("from selenium", low)
        self.assertNotIn("undetected_chromedriver", low)
        self.assertNotIn("import playwright", low)
        self.assertNotIn("from playwright", low)

    def test_probe_targets_only_official_product_pages_not_data_endpoints(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("https://www.wildberries.ru/catalog/{wb_sku}/detail.aspx", source)
        self.assertIn("https://www.ozon.ru/product/{ozon_sku}/", source)
        self.assertNotIn("card.wb.ru", source)
        self.assertNotIn("composer-api", source)
        self.assertNotIn("state-webPrice", source)

    def test_gate_treats_marketplace_http_antibot_as_reachability_but_rejects_proxy_failures(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn('"OZON_SITE_REACHABLE_ANTIBOT_RESPONSE"', source)
        self.assertIn('"SERVER_SEES_WB_AND_OZON"', source)
        self.assertIn("def _is_marketplace_http_response", source)
        self.assertIn("outcome.status_code == 407", source)
        self.assertIn('"proxy_auth_error"', source)
        self.assertIn('"proxy_connection_error"', source)
        self.assertIn('wb_reachable = bool(wb["marketplace_http_response_received"])', source)
        self.assertIn('ozon_reachable = bool(ozon["marketplace_http_response_received"])', source)

    def test_live_runner_calls_server_visibility_probe(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("tools\\probe_server_visibility.py", source)
        self.assertIn("SERVER_SEES_WB_AND_OZON", source)
        self.assertNotIn("probe_browser_visibility.py", source)


if __name__ == "__main__":
    unittest.main()
