from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from captcha.models import SliderSolveResult
from probe_ozon_solver_robustness_c24 import _classify_batch, _make_preview


def _png(image: Image.Image) -> bytes:
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class OzonSolverRobustnessC24Tests(unittest.TestCase):
    def test_batch_pass_requires_all_requested_runs_solved_with_continuity(self):
        results = [
            {"outcome": "solved", "continuity_ok": True},
            {"outcome": "solved", "continuity_ok": True},
            {"outcome": "solved", "continuity_ok": True},
        ]
        self.assertEqual(_classify_batch(results, 3), "OZON_SOLVER_ROBUSTNESS_PASS")

    def test_batch_partial_when_only_some_runs_solve(self):
        results = [
            {"outcome": "solved", "continuity_ok": True},
            {"outcome": "solver_uncertain", "continuity_ok": True},
            {"outcome": "blocked", "continuity_ok": False},
        ]
        self.assertEqual(_classify_batch(results, 3), "OZON_SOLVER_ROBUSTNESS_PARTIAL")

    def test_preview_is_written_for_structured_solution(self):
        background = Image.new("RGBA", (160, 90), (240, 240, 240, 255))
        piece = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        ImageDraw.Draw(piece).rectangle((5, 6, 30, 31), fill=(80, 100, 140, 255))
        solved = SliderSolveResult(True, "contour_edge_match", x=70, y=22, width=26, height=26, score=0.4, confidence=0.3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preview.png"
            self.assertTrue(_make_preview(_png(background), _png(piece), solved, path))
            self.assertTrue(path.exists())
            with Image.open(path) as image:
                self.assertEqual(image.size, (160, 90))

    def test_runtime_source_has_no_submission_or_historical_report_dependency(self):
        source = (ROOT / "tools" / "probe_ozon_solver_robustness_c24.py").read_text(encoding="utf-8").lower()
        forbidden = (
            "ozon_mobile_proxy_selector_report.json",
            "ozon_same_sticky_direct_c19_report.json",
            "/abt/captcha/result",
            "pointertrajectory",
            "pointer_trajectory",
            "selenium",
            "playwright",
            "2captcha",
            "nopecha",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_safe_contract_flags_are_present(self):
        source = (ROOT / "tools" / "probe_ozon_solver_robustness_c24.py").read_text(encoding="utf-8")
        self.assertIn('"challenge_submitted": False', source)
        self.assertIn('"credentials_persisted": False', source)
        self.assertIn('"full_urls_persisted": False', source)
        self.assertIn("OZON_SOLVER_ROBUSTNESS_PASS", source)


if __name__ == "__main__":
    unittest.main()
