from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from captcha.slider import solve_gap_by_difference, solve_piece_by_contour


def _png_bytes(image: Image.Image) -> bytes:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class LocalSliderSolverTests(unittest.TestCase):
    def test_contour_edge_match_finds_synthetic_gap(self):
        piece = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        pd = ImageDraw.Draw(piece)
        pd.rounded_rectangle((7, 8, 32, 33), radius=5, fill=(80, 120, 180, 255))

        target_x = 137
        target_y = 31
        background = Image.new("RGB", (240, 110), (220, 220, 220))
        bd = ImageDraw.Draw(background)
        # The gap boundary carries the same geometric contour as the piece.
        bd.rounded_rectangle(
            (target_x, target_y, target_x + 25, target_y + 25),
            radius=5,
            outline=(20, 20, 20),
            width=2,
        )

        result = solve_piece_by_contour(_png_bytes(piece), _png_bytes(background), min_confidence=0.02)
        self.assertTrue(result.ok, result.safe_dict())
        self.assertIsNotNone(result.x)
        self.assertIsNotNone(result.y)
        self.assertLessEqual(abs(result.x - target_x), 3, result.safe_dict())
        self.assertLessEqual(abs(result.y - target_y), 3, result.safe_dict())
        self.assertGreater(result.confidence, 0.0)

    def test_aligned_difference_finds_synthetic_gap(self):
        rng = np.random.default_rng(20260811)
        base = rng.integers(120, 220, size=(100, 240, 3), dtype=np.uint8)
        complete = Image.fromarray(base, mode="RGB")

        target_x = 92
        target_y = 26
        target_w = 34
        target_h = 42
        gapped_array = base.copy()
        gapped_array[target_y : target_y + target_h, target_x : target_x + target_w] = 25
        gapped = Image.fromarray(gapped_array, mode="RGB")

        result = solve_gap_by_difference(_png_bytes(gapped), _png_bytes(complete))
        self.assertTrue(result.ok, result.safe_dict())
        self.assertIsNotNone(result.x)
        self.assertLessEqual(abs(result.x - target_x), 5, result.safe_dict())
        self.assertGreater(result.confidence, 0.2)

    def test_difference_fails_closed_on_identical_images(self):
        image = Image.new("RGB", (180, 80), (120, 120, 120))
        raw = _png_bytes(image)
        result = solve_gap_by_difference(raw, raw)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "difference_signal_too_weak")

    def test_contour_fails_closed_on_background_without_edges(self):
        piece = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
        ImageDraw.Draw(piece).rectangle((5, 5, 24, 24), fill=(255, 255, 255, 255))
        background = Image.new("RGB", (160, 80), (127, 127, 127))
        result = solve_piece_by_contour(_png_bytes(piece), _png_bytes(background))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "background_has_no_edges")

    def test_runtime_source_has_no_external_solver_or_browser_dependency(self):
        package = CORE / "captcha"
        source = "\n".join(
            p.read_text(encoding="utf-8").lower()
            for p in package.glob("*.py")
        )
        forbidden = (
            "2captcha",
            "nopecha",
            "solvecaptcha",
            "nocaptcha",
            "http://",
            "https://",
            "playwright",
            "selenium",
            "undetected_chromedriver",
        )
        for token in forbidden:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
