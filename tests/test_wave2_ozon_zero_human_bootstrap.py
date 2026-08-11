from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_ozon_zero_human_bootstrap.py"
PROMPT = ROOT / "prompts" / "work" / "G01-SG04" / "PR01-ST01-T01-C08.I01.md"
RUNNER = ROOT / "tests" / "RUN_OZON_BOOTSTRAP_PROBE.bat"
MAIN_LIVE_RUNNER = ROOT / "tests" / "RUN_WAVE2_LIVE_PROBES.bat"
LINUX_SETUP = ROOT / "tests" / "setup_ozon_bootstrap.sh"


class OzonZeroHumanBootstrapContractTests(unittest.TestCase):
    def test_probe_uses_headless_playwright_only_for_bootstrap_then_curl_replay(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("LocalBrowserProxyBridge(context)", source)
        self.assertIn("headless=True", source)
        self.assertIn('page.on("request", observe)', source)
        self.assertIn("ENTRYPOINT_MARKER", source)
        self.assertIn("curl_request_via_proxy", source)
        self.assertLess(source.index("browser.close()"), source.index("curl_request_via_proxy(\n            context"))

    def test_probe_does_not_pin_stale_o3_versions_or_persist_secret_headers(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertNotIn("release_24-6-2026", source)
        self.assertNotIn("e801a3c6", source)
        self.assertIn('SECRET_HEADER_NAMES = {"cookie", "authorization", "proxy-authorization"}', source)
        self.assertIn('"secret_headers_persisted": False', source)

    def test_bootstrap_cycle_does_not_claim_price_semantics(self):
        source = PROBE.read_text(encoding="utf-8")
        prompt = PROMPT.read_text(encoding="utf-8")
        self.assertIn('"price_parsed": False', source)
        self.assertIn("Do **not** parse or claim the final price field", prompt)
        self.assertIn("no manual captcha solving", prompt.lower())
        self.assertIn("no manual city/PVZ selection", prompt)

    def test_ozon_runner_is_separate_from_active_wb_live_runner(self):
        runner = RUNNER.read_text(encoding="utf-8")
        main_runner = MAIN_LIVE_RUNNER.read_text(encoding="utf-8")
        self.assertIn("probe_ozon_zero_human_bootstrap.py", runner)
        self.assertNotIn("probe_ozon_zero_human_bootstrap.py", main_runner)
        self.assertIn("probe_wb_current_endpoint.py", main_runner)

    def test_linux_setup_installs_playwright_and_chromium_dependencies(self):
        source = LINUX_SETUP.read_text(encoding="utf-8")
        self.assertIn('pip install "playwright>=1.40"', source)
        self.assertIn("playwright install-deps chromium", source)
        self.assertIn("playwright install chromium", source)


if __name__ == "__main__":
    unittest.main()
