from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOLVER = ROOT / "tools" / "ozon_captcha_solver_once.py"
HANDOFF = ROOT / "tools" / "ozon_captcha_human_handoff_price.py"


class OzonCaptchaSplitScriptsTests(unittest.TestCase):
    def test_solver_script_parses(self):
        ast.parse(SOLVER.read_text(encoding="utf-8"))

    def test_handoff_script_parses(self):
        ast.parse(HANDOFF.read_text(encoding="utf-8"))

    def test_solver_has_no_submission_or_browser(self):
        source = SOLVER.read_text(encoding="utf-8").lower()
        self.assertIn("solve_piece_by_contour", source)
        self.assertIn('"challenge_submitted": false', source)
        for forbidden in (
            "/abt/captcha/result",
            "undetected_chromedriver",
            "selenium",
            "actionchains",
            "drag_and_drop",
        ):
            self.assertNotIn(forbidden, source)

    def test_handoff_requires_human_action(self):
        source = HANDOFF.read_text(encoding="utf-8").lower()
        self.assertIn('input("enter after captcha is accepted:', source)
        self.assertIn("visible chrome", source)
        for forbidden in (
            "/abt/captcha/result",
            "actionchains",
            "drag_and_drop",
            "pointertrajectory",
            "pointer_trajectory",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
