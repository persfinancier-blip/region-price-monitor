from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_ozon_curl_guest_bootstrap.py"
RUNNER = ROOT / "tests" / "RUN_OZON_CURL_GUEST_BOOTSTRAP.bat"
PROMPT = ROOT / "prompts" / "work" / "G01-SG04" / "PR01-ST01-T01-C12.I01.md"


class OzonCurlGuestBootstrapTests(unittest.TestCase):
    def test_probe_starts_from_empty_curl_session_and_reuses_same_session(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn('session = creq.Session(impersonate="chrome")', source)
        self.assertGreaterEqual(source.count("session=session"), 3)
        self.assertNotIn("DEFAULT_COOKIE_FILE", source)
        self.assertNotIn("_load_cookie_file", source)

    def test_probe_has_no_browser_runtime_or_login_inputs(self):
        source = PROBE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "from playwright",
            "import playwright",
            "sync_playwright(",
            "chromium.launch(",
            "selenium.webdriver",
            "ozon_login",
            "ozon_password",
        ):
            self.assertNotIn(forbidden, source)

    def test_challenge_json_cannot_count_as_product_binding(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn('CHALLENGE_KEYS = {"challengeURL", "blockURL", "incidentId"}', source)
        self.assertIn("and not challenged_api", source)
        self.assertIn('"challenge_json": challenged_api', source)
        self.assertIn('"requested_sku_bound": exact_sku_bound', source)

    def test_safe_report_exposes_cookie_names_not_values(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn('"cookie_names_after_home": cookies_after_home', source)
        self.assertIn('"cookie_values_persisted": False', source)
        self.assertNotIn('"cookie_values":', source)

    def test_runner_and_prompt_are_c12(self):
        runner = RUNNER.read_text(encoding="utf-8")
        prompt = PROMPT.read_text(encoding="utf-8")
        self.assertIn("probe_ozon_curl_guest_bootstrap.py", runner)
        self.assertIn("C12.I01", prompt)
        self.assertIn("no cookie file", prompt.lower())
        self.assertIn("region comparison", prompt.lower())


if __name__ == "__main__":
    unittest.main()
