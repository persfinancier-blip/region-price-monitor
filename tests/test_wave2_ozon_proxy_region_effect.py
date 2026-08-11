from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_ozon_proxy_region_effect.py"
RUNNER = ROOT / "tests" / "RUN_OZON_PROXY_REGION_PROBE.bat"
PROMPT = ROOT / "prompts" / "work" / "G01-SG04" / "PR01-ST01-T01-C10.I01.md"


class OzonProxyRegionEffectTests(unittest.TestCase):
    def test_probe_changes_only_proxy_context_and_reuses_same_cookie_state(self):
        source = PROBE.read_text(encoding="utf-8")
        low = source.lower()
        self.assertIn('"same_for_both_runs": True', source)
        self.assertIn("cookie_sha", source)
        self.assertIn("context_a = _make_context", source)
        self.assertIn("context_b = _make_context", source)

        # C10 may mention Playwright in human-readable diagnostics, but it must
        # not import or invoke any browser runtime. Test behavior/authority, not words.
        self.assertNotIn("from playwright", low)
        self.assertNotIn("import playwright", low)
        self.assertNotIn("sync_playwright(", low)
        self.assertNotIn("chromium.launch(", low)
        self.assertNotIn("browser.new_context(", low)
        self.assertNotIn("page.goto(", low)
        self.assertNotIn("selenium", low)
        self.assertNotIn("undetected_chromedriver", low)
        self.assertNotIn("ozon_login", low)
        self.assertNotIn("ozon_password", low)

    def test_probe_uses_exact_entrypoint_and_strict_product_widget_selection(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("/api/entrypoint-api.bx/page/json/v2", source)
        self.assertIn('block.get("component") != component_name', source)
        self.assertIn('state_id = block.get("stateId")', source)
        self.assertIn('"ambiguous_price_widgets"', source)
        self.assertIn('sku not in str(page_url)', source)

    def test_equal_price_is_inconclusive_not_negative_proof(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("OZON_PROXY_REGION_EFFECT_INCONCLUSIVE_SAME_VALUE", source)
        prompt = PROMPT.read_text(encoding="utf-8")
        self.assertIn("Equal prices are inconclusive", prompt)

    def test_runner_targets_c10_probe(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("probe_ozon_proxy_region_effect.py", source)


if __name__ == "__main__":
    unittest.main()
