from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_browser_visibility.py"
RUNNER = ROOT / "tests" / "RUN_WAVE2_LIVE_PROBES.bat"


class VisibleBrowserSmokeContractTests(unittest.TestCase):
    def test_probe_is_visible_and_targets_real_marketplace_pages_only(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertNotIn("--headless", source)
        self.assertIn("https://www.wildberries.ru/catalog/{wb_sku}/detail.aspx", source)
        self.assertIn("https://www.ozon.ru/product/{ozon_sku}/", source)
        self.assertNotIn("card.wb.ru", source)
        self.assertNotIn("composer-api", source)

    def test_probe_reads_neutral_identity_with_browser_fetch_not_json_viewer_dom(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("def _browser_fetch_text", source)
        self.assertIn("driver.execute_async_script", source)
        self.assertIn("neutral_fetch = _browser_fetch_text(driver, NEUTRAL_URL)", source)
        self.assertIn('identity = _parse_identity(neutral_fetch.get("text") or "")', source)

    def test_probe_saves_local_marketplace_screenshots(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("driver.save_screenshot", source)
        self.assertIn('"browser_visibility_wb.png"', source)
        self.assertIn('"browser_visibility_ozon.png"', source)

    def test_live_runner_no_longer_uses_browser_smoke(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertNotIn("tools\\probe_browser_visibility.py", source)
        # Do not pin the live runner to one later evidence phase. C06 only owns the
        # invariant that browser smoke is historical and cannot become the active runner again.
        self.assertTrue(
            "tools\\probe_server_visibility.py" in source
            or "tools\\probe_wb_current_endpoint.py" in source
        )


if __name__ == "__main__":
    unittest.main()
