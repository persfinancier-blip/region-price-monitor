"""Repository-owned local CAPTCHA image analysis primitives.

The package contains only local algorithms. It does not call remote CAPTCHA
solving services and does not perform browser automation.
"""

from .models import SliderSolveResult
from .slider import solve_gap_by_difference, solve_piece_by_contour

__all__ = [
    "SliderSolveResult",
    "solve_gap_by_difference",
    "solve_piece_by_contour",
]
