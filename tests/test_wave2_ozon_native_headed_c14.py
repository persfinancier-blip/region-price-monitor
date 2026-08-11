from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_ozon_native_headed_c14.py"
RUNNER = ROOT / "tests" / "RUN_OZON_NATIVE_HEADED_C14.bat"
PROMPT = ROOT / "prompts" / "work" / "G01-SG04" / "PR01-ST01-T01-C14.I01.md"


class OzonNativeHeadedC14Tests(unittest.TestCase):
    def test_probe_uses_native_playwright_proxy_not_loopback_bridge(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn('"server": f"{context.scheme}://{host}:{context.port}"', source)
        self.assertIn('"username": context.proxy_user', source)
        self.assertIn('"password": context.proxy_password', source)
        self.assertNotIn("LocalBrowserProxyBridge", source)
        self.assertIn("headless=False", source)

    def test_probe_requires_same_neutral_identity_before_ozon_evidence(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("_same_identity(curl_identity, result.get(\"neutral_identity\"))", source)
        self.assertIn("OZON_NATIVE_HEADED_PROXY_BINDING_FAILED", source)

    def test_probe_types_block_without_solving_it(self):
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("OZON_NATIVE_HEADED_BLOCKED", source)
        self.assertNotIn("captcha-input", source)
        self.assertNotIn("slider", source.lower())
        prompt = PROMPT.read_text(encoding="utf-8")
        self.assertIn("No captcha solving or bypass is permitted", prompt)

    def test_runner_targets_c14_probe(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("probe_ozon_native_headed_c14.py", source)


if __name__ == "__main__":
    unittest.main()
