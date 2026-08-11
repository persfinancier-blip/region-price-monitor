from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
TESTS = ROOT / "tests"


class OzonSameStickyC19Tests(unittest.TestCase):
    def test_runner_targets_c19_probe(self):
        source = (TESTS / "RUN_OZON_SAME_STICKY_DIRECT_C19.bat").read_text(encoding="utf-8")
        self.assertIn("probe_ozon_same_sticky_direct_c19.py", source)

    def test_probe_reuses_c18_selected_session(self):
        source = (TOOLS / "probe_ozon_same_sticky_direct_c19.py").read_text(encoding="utf-8")
        self.assertIn("ozon_mobile_proxy_selector_report.json", source)
        self.assertIn("rotate_session(proxy_user, c18_session_id)", source)
        self.assertIn("neutral_ip != c18_ip", source)

    def test_probe_is_zero_cookie_and_browser_free(self):
        source = (TOOLS / "probe_ozon_same_sticky_direct_c19.py").read_text(encoding="utf-8").lower()
        forbidden = (
            "getpass",
            "from playwright",
            "import playwright",
            "selenium",
            "chromium.launch",
            'cookies=',
            '"https://www.ozon.ru/"',
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertIn("api_url", source)
        self.assertIn("zero_cookie_request", source)


if __name__ == "__main__":
    unittest.main()
