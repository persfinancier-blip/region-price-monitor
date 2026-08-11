from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
from PIL import Image

from .models import SliderSolveResult


class SliderImageError(ValueError):
    pass


def _as_rgba(image: bytes | bytearray | Image.Image) -> np.ndarray:
    try:
        if isinstance(image, Image.Image):
            pil = image.convert("RGBA")
        elif isinstance(image, (bytes, bytearray)):
            pil = Image.open(BytesIO(bytes(image))).convert("RGBA")
        else:
            raise TypeError("image must be bytes, bytearray or PIL.Image.Image")
        array = np.asarray(pil, dtype=np.uint8)
    except Exception as exc:
        raise SliderImageError(f"invalid image: {type(exc).__name__}: {exc}") from exc
    if array.ndim != 3 or array.shape[2] != 4 or array.shape[0] < 2 or array.shape[1] < 2:
        raise SliderImageError("image must decode to RGBA with width/height >= 2")
    return array


def _gray(rgba: np.ndarray) -> np.ndarray:
    rgb = rgba[..., :3].astype(np.float32)
    return (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114) / 255.0


def _edge_map(gray: np.ndarray) -> np.ndarray:
    """Small dependency-free Sobel-like gradient magnitude in [0, 1]."""
    gx = np.zeros_like(gray, dtype=np.float32)
    gy = np.zeros_like(gray, dtype=np.float32)
    gx[:, 1:-1] = (gray[:, 2:] - gray[:, :-2]) * 0.5
    gy[1:-1, :] = (gray[2:, :] - gray[:-2, :]) * 0.5
    mag = np.hypot(gx, gy)
    scale = float(np.percentile(mag, 99.5)) if mag.size else 0.0
    if scale <= 1e-9:
        return np.zeros_like(mag)
    return np.clip(mag / scale, 0.0, 1.0)


def _alpha_bbox(alpha: np.ndarray, threshold: int = 24) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(alpha > threshold)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _contour(mask: np.ndarray) -> np.ndarray:
    """Return one-pixel inside contour of a boolean alpha mask."""
    padded = np.pad(mask.astype(bool), 1, mode="constant", constant_values=False)
    center = padded[1:-1, 1:-1]
    interior = (
        center
        & padded[:-2, 1:-1]
        & padded[2:, 1:-1]
        & padded[1:-1, :-2]
        & padded[1:-1, 2:]
    )
    return center & ~interior


def solve_piece_by_contour(
    piece: bytes | bytearray | Image.Image,
    background: bytes | bytearray | Image.Image,
    *,
    min_score: float = 0.12,
    min_confidence: float = 0.06,
) -> SliderSolveResult:
    """Locate a slider gap by matching the movable piece contour to background edges.

    This is a clean-room generic image algorithm. It does not know any target
    website or CAPTCHA protocol and performs no network requests.
    """
    strategy = "contour_edge_match"
    try:
        piece_rgba = _as_rgba(piece)
        bg_rgba = _as_rgba(background)
    except SliderImageError as exc:
        return SliderSolveResult(False, strategy, error=str(exc))

    bbox = _alpha_bbox(piece_rgba[..., 3])
    if bbox is None:
        return SliderSolveResult(False, strategy, error="piece_alpha_mask_empty")
    x0, y0, x1, y1 = bbox
    piece_crop = piece_rgba[y0:y1, x0:x1]
    mask = piece_crop[..., 3] > 24
    contour = _contour(mask)
    cy, cx = np.nonzero(contour)
    if cx.size < 8:
        return SliderSolveResult(False, strategy, error="piece_contour_too_small")

    ph, pw = contour.shape
    bh, bw = bg_rgba.shape[:2]
    if pw > bw or ph > bh:
        return SliderSolveResult(False, strategy, error="piece_larger_than_background")

    edges = _edge_map(_gray(bg_rgba))
    if float(edges.max()) <= 1e-9:
        return SliderSolveResult(False, strategy, error="background_has_no_edges")

    best_score = -1.0
    best_x = 0
    best_y = 0
    candidates: list[tuple[float, int, int]] = []

    # CAPTCHA images are small; a direct scan is deterministic and avoids a
    # heavyweight CV runtime. Only contour pixels are scored.
    for y in range(0, bh - ph + 1):
        rows = y + cy
        for x in range(0, bw - pw + 1):
            score = float(edges[rows, x + cx].mean())
            if score > best_score:
                best_score, best_x, best_y = score, x, y
            candidates.append((score, x, y))

    # Nearby offsets around the same physical gap are not an independent
    # runner-up. Exclude a neighborhood before estimating ambiguity.
    exclusion_x = max(3, pw // 3)
    exclusion_y = max(3, ph // 3)
    independent = [
        score
        for score, x, y in candidates
        if abs(x - best_x) > exclusion_x or abs(y - best_y) > exclusion_y
    ]
    runner_up = max(independent) if independent else 0.0
    confidence = max(0.0, (best_score - runner_up) / max(best_score, 1e-9))

    if best_score < min_score:
        return SliderSolveResult(
            False,
            strategy,
            x=best_x,
            y=best_y,
            width=pw,
            height=ph,
            score=best_score,
            confidence=confidence,
            error="edge_signal_too_weak",
        )
    if confidence < min_confidence:
        return SliderSolveResult(
            False,
            strategy,
            x=best_x,
            y=best_y,
            width=pw,
            height=ph,
            score=best_score,
            confidence=confidence,
            error="ambiguous_edge_match",
        )

    return SliderSolveResult(
        True,
        strategy,
        x=best_x,
        y=best_y,
        width=pw,
        height=ph,
        score=best_score,
        confidence=confidence,
    )


def _smooth_1d(values: np.ndarray, width: int = 5) -> np.ndarray:
    if width <= 1 or values.size < width:
        return values.astype(np.float32, copy=True)
    kernel = np.ones(width, dtype=np.float32) / float(width)
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def solve_gap_by_difference(
    gapped: bytes | bytearray | Image.Image,
    complete: bytes | bytearray | Image.Image,
    *,
    min_peak: float = 0.035,
    min_confidence: float = 0.20,
) -> SliderSolveResult:
    """Locate the changed/gap region from aligned gapped and complete images."""
    strategy = "aligned_image_difference"
    try:
        gap_rgba = _as_rgba(gapped)
        full_rgba = _as_rgba(complete)
    except SliderImageError as exc:
        return SliderSolveResult(False, strategy, error=str(exc))

    if gap_rgba.shape[:2] != full_rgba.shape[:2]:
        return SliderSolveResult(False, strategy, error="image_dimensions_differ")

    diff = np.abs(_gray(gap_rgba) - _gray(full_rgba))
    if diff.size == 0:
        return SliderSolveResult(False, strategy, error="empty_difference")

    column = _smooth_1d(diff.mean(axis=0), width=5)
    peak = float(column.max())
    if peak < min_peak:
        return SliderSolveResult(
            False,
            strategy,
            score=peak,
            confidence=0.0,
            error="difference_signal_too_weak",
        )

    peak_x = int(np.argmax(column))
    threshold = max(float(np.median(column)) + peak * 0.12, peak * 0.38)

    left = peak_x
    while left > 0 and column[left - 1] >= threshold:
        left -= 1
    right = peak_x
    while right + 1 < column.size and column[right + 1] >= threshold:
        right += 1

    region = diff[:, left : right + 1]
    row = _smooth_1d(region.mean(axis=1), width=3)
    peak_y = int(np.argmax(row))
    row_threshold = max(float(np.median(row)) + float(row.max()) * 0.12, float(row.max()) * 0.38)
    top = peak_y
    while top > 0 and row[top - 1] >= row_threshold:
        top -= 1
    bottom = peak_y
    while bottom + 1 < row.size and row[bottom + 1] >= row_threshold:
        bottom += 1

    outside = np.concatenate((column[:left], column[right + 1 :]))
    runner = float(np.percentile(outside, 99.0)) if outside.size else 0.0
    confidence = max(0.0, (peak - runner) / max(peak, 1e-9))

    if confidence < min_confidence:
        return SliderSolveResult(
            False,
            strategy,
            x=left,
            y=top,
            width=right - left + 1,
            height=bottom - top + 1,
            score=peak,
            confidence=confidence,
            error="ambiguous_difference",
        )

    return SliderSolveResult(
        True,
        strategy,
        x=left,
        y=top,
        width=right - left + 1,
        height=bottom - top + 1,
        score=peak,
        confidence=confidence,
    )
