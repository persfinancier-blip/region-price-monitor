from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from probe_ozon_captcha_geometry_c25 import _compute_geometry


class OzonCaptchaGeometryC25Tests(unittest.TestCase):
    def test_geometry_scale_one_with_alpha_padding(self):
        result = _compute_geometry(
            image_rect={"left": 100, "top": 50, "width": 400, "height": 300},
            puzzle_rect={"left": 120, "top": 80, "width": 110, "height": 100},
            background_natural=(400, 300),
            puzzle_natural=(110, 100),
            alpha_bbox={"x0": 10, "y0": 7},
            solver_x=189,
            solver_y=89,
        )
        self.assertAlmostEqual(result["target_shape_left"], 289.0)
        self.assertAlmostEqual(result["target_shape_top"], 139.0)
        self.assertAlmostEqual(result["target_element_left"], 279.0)
        self.assertAlmostEqual(result["target_element_top"], 132.0)
        self.assertAlmostEqual(result["delta_x"], 159.0)
        self.assertAlmostEqual(result["delta_y"], 52.0)

    def test_geometry_non_unit_scale(self):
        result = _compute_geometry(
            image_rect={"left": 20, "top": 30, "width": 800, "height": 600},
            puzzle_rect={"left": 100, "top": 110, "width": 220, "height": 200},
            background_natural=(400, 300),
            puzzle_natural=(110, 100),
            alpha_bbox={"x0": 10, "y0": 5},
            solver_x=200,
            solver_y=100,
        )
        self.assertAlmostEqual(result["background_scale_x"], 2.0)
        self.assertAlmostEqual(result["puzzle_scale_x"], 2.0)
        self.assertAlmostEqual(result["target_element_left"], 400.0)
        self.assertAlmostEqual(result["target_element_top"], 220.0)
        self.assertAlmostEqual(result["delta_x"], 300.0)
        self.assertAlmostEqual(result["delta_y"], 110.0)

    def test_invalid_dimensions_fail_closed(self):
        with self.assertRaises(ValueError):
            _compute_geometry(
                image_rect={"left": 0, "top": 0, "width": 0, "height": 300},
                puzzle_rect={"left": 0, "top": 0, "width": 100, "height": 100},
                background_natural=(400, 300),
                puzzle_natural=(100, 100),
                alpha_bbox={"x0": 0, "y0": 0},
                solver_x=1,
                solver_y=1,
            )

    def test_runtime_source_has_no_submission_or_pointer_automation(self):
        source = (ROOT / "tools" / "probe_ozon_captcha_geometry_c25.py").read_text(encoding="utf-8").lower()
        forbidden = (
            "ozon_mobile_proxy_selector_report.json",
            "ozon_same_sticky_direct_c19_report.json",
            "/abt/captcha/result",
            "actionchains",
            ".click(",
            "drag_and_drop",
            "move_by_offset",
            "dispatch_event",
            "pointerdown",
            "pointermove",
            "pointerup",
            "mousedown",
            "mousemove",
            "mouseup",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_safe_contract_flags_are_present(self):
        source = (ROOT / "tools" / "probe_ozon_captcha_geometry_c25.py").read_text(encoding="utf-8")
        self.assertIn('"challenge_submitted": False', source)
        self.assertIn('"browser_actions_performed": False', source)
        self.assertIn('"credentials_persisted": False', source)
        self.assertIn('"full_urls_persisted": False', source)
        self.assertIn("OZON_CAPTCHA_DOM_GEOMETRY_CALIBRATED", source)


if __name__ == "__main__":
    unittest.main()
