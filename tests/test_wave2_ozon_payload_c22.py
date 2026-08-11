from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from captcha.ozon_payload import (
    OzonEmbeddedChallengeError,
    decode_captcha_url,
    raw_query_value,
)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").rstrip("=")


def _fixture_url(*, image="https://img.example/a.png", puzzle="https://img.example/b.png") -> str:
    inner = _b64(json.dumps({
        "pp": [12, 34, 400],
        "cb": [0.1, 0.2],
        "support_domain": "example.invalid",
        "origin_referer": "example.invalid",
        "ts": 123456,
        "is": image,
        "ps": puzzle,
    }).encode())
    token = f"cp:segment-a:segment-b:{inner}"
    outer = _b64(f"11,fixture-id,{token}".encode())
    return f"https://example.invalid/captcha.html?captcha=abc{outer}&mode=m"


class OzonPayloadC22Tests(unittest.TestCase):
    def test_decodes_structural_fixture(self) -> None:
        payload = decode_captcha_url(_fixture_url())
        self.assertEqual(payload.version, "11")
        self.assertEqual(payload.opaque_prefix_length, 3)
        self.assertEqual(payload.pp, (12.0, 34.0, 400.0))
        self.assertEqual(payload.cb, (0.1, 0.2))
        self.assertEqual(payload.image_url, "https://img.example/a.png")
        self.assertEqual(payload.puzzle_url, "https://img.example/b.png")

    def test_raw_query_preserves_plus(self) -> None:
        self.assertEqual(raw_query_value("https://x.invalid/?captcha=A+B", "captcha"), "A+B")
        self.assertEqual(raw_query_value("https://x.invalid/?captcha=A%2BB", "captcha"), "A+B")

    def test_bad_outer_fails_closed(self) -> None:
        with self.assertRaises(OzonEmbeddedChallengeError):
            decode_captcha_url("https://example.invalid/captcha.html?captcha=broken")

    def test_non_https_image_fails_closed(self) -> None:
        with self.assertRaises(OzonEmbeddedChallengeError):
            decode_captcha_url(_fixture_url(image="http://img.example/a.png"))

    def test_credential_bearing_image_fails_closed(self) -> None:
        with self.assertRaises(OzonEmbeddedChallengeError):
            decode_captcha_url(_fixture_url(puzzle="https://user:pass@img.example/b.png"))

    def test_safe_dict_excludes_raw_token_and_full_urls(self) -> None:
        payload = decode_captcha_url(_fixture_url())
        safe = payload.safe_dict()
        text = json.dumps(safe)
        self.assertNotIn(payload.token, text)
        self.assertNotIn(payload.image_url, text)
        self.assertNotIn(payload.puzzle_url, text)
        self.assertFalse(safe["raw_token_persisted"])
        self.assertFalse(safe["full_urls_persisted"])


if __name__ == "__main__":
    unittest.main()
