from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_ozon_access_discriminator.py"
RUNNER = ROOT / "tests" / "RUN_OZON_ACCESS_DIAGNOSTIC.bat"


class OzonAccessDiscriminatorTests(unittest.TestCase):
    def test_probe_compares_headless_and_headed_through_same_proxy_context(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("LocalBrowserProxyBridge(context)", source)
        self.assertIn("headless=True", source)
        self.assertIn("headless=False", source)
        self.assertIn("proxy={\"server\": bridge.proxy_url}", source)
        self.assertIn("proxy_binding_same_identity_all_modes", source)

    def test_probe_recognizes_exact_ozon_network_denial_as_typed_evidence(self):
        source = PROBE.read_text(encoding="utf-8").lower()
        self.assertIn("похоже, нет соединения", source)
        self.assertIn("выключите vpn", source)
        self.assertIn("ozon_route_denied_both_browser_modes", source)
        self.assertIn("ozon_headless_specific_denial_evidenced", source)

    def test_probe_remains_zero_user_and_does_not_add_ozon_credentials_or_profile_state(self):
        source = PROBE.read_text(encoding="utf-8").lower()
        self.assertNotIn("ozon_password", source)
        self.assertNotIn("ozon_login", source)
        self.assertNotIn("storage_state=", source)
        self.assertNotIn("cookie_file", source)
        self.assertNotIn("cookies_from_curl", source)

    def test_runner_targets_only_c09_discriminator(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("tools\\probe_ozon_access_discriminator.py", source)
        self.assertNotIn("probe_browser_visibility.py", source)


if __name__ == "__main__":
    unittest.main()
