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

    def test_probe_saves_local_marketplace_screenshots(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("driver.save_screenshot", source)
        self.assertIn('"browser_visibility_wb.png"', source)
        self.assertIn('"browser_visibility_ozon.png"', source)

    def test_runner_calls_visibility_probe(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("tools\\probe_browser_visibility.py", source)
        self.assertNotIn("tools\\probe_wave2_live.py", source)


if __name__ == "__main__":
    unittest.main()
