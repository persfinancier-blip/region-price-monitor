from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import analyze_ozon_captcha_protocol_c21 as c21


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").rstrip("=")


class C21ProtocolTests(unittest.TestCase):
    def _fixture(self) -> str:
        inner = _b64(json.dumps({"pp": [10, 20, 300], "is": "https://img.example/a.png", "ps": "https://img.example/b.png"}).encode())
        outer = f"11,fixture-id,cp:one:two:{inner}".encode()
        return "xyz" + _b64(outer)

    def test_structural_decode_discovers_opaque_prefix(self) -> None:
        result = c21._decode_captcha_structure(self._fixture())
        self.assertTrue(result["structured"])
        self.assertEqual(result["opaque_prefix_length"], 3)
        self.assertEqual(result["outer_field_count"], 3)
        self.assertEqual(result["token_segment_count"], 4)
        self.assertEqual(result["inner_decoded_type"], "dict")
        self.assertEqual(result["inner_json_keys"], ["is", "pp", "ps"])

    def test_raw_query_preserves_literal_plus(self) -> None:
        pairs = c21._raw_query("https://example.invalid/x?alpha=A+B&beta=C%2BD")
        self.assertEqual(pairs, [("alpha", "A+B"), ("beta", "C+D")])

    def test_malformed_payload_fails_closed(self) -> None:
        result = c21._decode_captcha_structure("not-valid")
        self.assertFalse(result["structured"])

    def test_decode_metadata_does_not_emit_source_value(self) -> None:
        source = self._fixture()
        result = c21._decode_captcha_structure(source)
        serialized = json.dumps(result)
        self.assertNotIn(source, serialized)
        self.assertIn("value_sha256", result)


if __name__ == "__main__":
    unittest.main()
