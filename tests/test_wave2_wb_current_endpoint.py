from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_wb_current_endpoint.py"
RUNNER = ROOT / "tests" / "RUN_WAVE2_LIVE_PROBES.bat"


class WBCurrentEndpointProbeTests(unittest.TestCase):
    def test_probe_targets_owner_supplied_current_internal_endpoint(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("https://www.wildberries.ru/__internal/u-card/cards/v4/detail", source)
        self.assertIn('"hide_vflags": "4294967296"', source)
        self.assertIn('"hide_dtype": "15"', source)
        self.assertIn('"mtype": "257"', source)
        self.assertIn('"ab_testing": "false"', source)

    def test_probe_is_server_only_and_does_not_embed_browser_secrets(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("from requests_transport import request_via_proxy", source)
        self.assertNotIn("undetected_chromedriver", source)
        self.assertNotIn("from selenium", source)
        self.assertNotIn("from playwright", source)
        self.assertNotIn("wbx-validation-key", source)
        self.assertNotIn("x_wbaas_token", source)
        self.assertNotIn("__zzatw-wb", source)
        self.assertNotIn("cfidsw-wb", source)

    def test_data_access_requires_requested_sku_in_json_not_http_only(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("json_ok and requested_sku_found", source)
        self.assertIn('"WB_CURRENT_ENDPOINT_DATA_ACCESS_PROVEN"', source)
        self.assertIn('"WB_CURRENT_ENDPOINT_REACHABLE_BUT_BLOCKED"', source)

    def test_live_runner_calls_current_wb_endpoint_probe(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("tools\\probe_wb_current_endpoint.py", source)
        self.assertNotIn("probe_server_visibility.py", source)
        self.assertNotIn("probe_browser_visibility.py", source)


if __name__ == "__main__":
    unittest.main()
