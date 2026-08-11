from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SliderSolveResult:
    """Structured fail-closed result for a local slider/puzzle image solve."""

    ok: bool
    strategy: str
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    score: float = 0.0
    confidence: float = 0.0
    error: str | None = None

    def safe_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "strategy": self.strategy,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "score": round(float(self.score), 6),
            "confidence": round(float(self.confidence), 6),
            "error": self.error,
        }
