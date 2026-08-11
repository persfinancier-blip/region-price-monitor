from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from captcha.slider import solve_gap_by_difference, solve_piece_by_contour

CAPTURE_DIR = CORE / "local" / "probes" / "ozon_challenge_c20"
REPORT_FILE = CORE / "local" / "probes" / "ozon_solver_c20_eval_report.json"
PREVIEW_FILE = CORE / "local" / "probes" / "ozon_solver_c20_preview.png"


@dataclass(frozen=True)
class LocalImage:
    path: Path
    width: int
    height: int
    mode: str
    has_alpha: bool
    alpha_transparent_fraction: float

    @property
    def area(self) -> int:
        return self.width * self.height

    def safe_dict(self) -> dict[str, Any]:
        return {
            "file": self.path.name,
            "width": self.width,
            "height": self.height,
            "mode": self.mode,
            "has_alpha": self.has_alpha,
            "alpha_transparent_fraction": round(self.alpha_transparent_fraction, 6),
        }


def _inspect_image(path: Path) -> LocalImage | None:
    try:
        with Image.open(path) as image:
            image.load()
            width, height = int(image.width), int(image.height)
            mode = str(image.mode)
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            extrema = alpha.getextrema()
            has_alpha = mode in {"RGBA", "LA", "PA"} or "transparency" in image.info or extrema != (255, 255)
            histogram = alpha.histogram()
            total = max(1, width * height)
            transparent = sum(histogram[:250])
            transparent_fraction = transparent / float(total)
            return LocalImage(
                path=path,
                width=width,
                height=height,
                mode=mode,
                has_alpha=bool(has_alpha),
                alpha_transparent_fraction=float(transparent_fraction),
            )
    except Exception:
        return None


def _discover_images() -> list[LocalImage]:
    if not CAPTURE_DIR.exists():
        return []
    images: list[LocalImage] = []
    for path in sorted(CAPTURE_DIR.iterdir()):
        if not path.is_file():
            continue
        item = _inspect_image(path)
        if item is not None:
            images.append(item)
    return images


def _read(path: Path) -> bytes:
    return path.read_bytes()


def _piece_candidates(images: list[LocalImage]) -> list[LocalImage]:
    if not images:
        return []
    max_area = max(image.area for image in images)
    candidates = [
        image
        for image in images
        if image.has_alpha
        and image.alpha_transparent_fraction >= 0.02
        and image.area <= max_area * 0.60
    ]
    return sorted(candidates, key=lambda image: (image.area, -image.alpha_transparent_fraction))


def _run_contour(images: list[LocalImage]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for piece in _piece_candidates(images):
        for background in images:
            if background.path == piece.path:
                continue
            if background.width < piece.width or background.height < piece.height:
                continue
            result = solve_piece_by_contour(_read(piece.path), _read(background.path), min_confidence=0.02)
            results.append(
                {
                    "kind": "piece_background",
                    "piece": piece.path.name,
                    "background": background.path.name,
                    "result": result.safe_dict(),
                }
            )
    return results


def _run_difference(images: list[LocalImage]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, first in enumerate(images):
        for second in images[index + 1 :]:
            if (first.width, first.height) != (second.width, second.height):
                continue
            result = solve_gap_by_difference(_read(first.path), _read(second.path))
            results.append(
                {
                    "kind": "aligned_pair",
                    "gapped_or_first": first.path.name,
                    "complete_or_second": second.path.name,
                    "result": result.safe_dict(),
                }
            )
    return results


def _successful(all_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    successful = [item for item in all_results if bool((item.get("result") or {}).get("ok"))]
    successful.sort(
        key=lambda item: (
            float((item.get("result") or {}).get("confidence") or 0.0),
            float((item.get("result") or {}).get("score") or 0.0),
        ),
        reverse=True,
    )
    return successful


def _find_image(images: list[LocalImage], name: str) -> LocalImage | None:
    for image in images:
        if image.path.name == name:
            return image
    return None


def _write_preview(best: dict[str, Any], images: list[LocalImage]) -> bool:
    result = best.get("result") or {}
    x = result.get("x")
    y = result.get("y")
    width = result.get("width")
    height = result.get("height")
    if None in {x, y, width, height}:
        return False

    if best.get("kind") == "piece_background":
        name = str(best.get("background") or "")
    else:
        name = str(best.get("gapped_or_first") or "")

    image = _find_image(images, name)
    if image is None:
        return False

    try:
        with Image.open(image.path) as source:
            preview = source.convert("RGB")
        draw = ImageDraw.Draw(preview)
        x0, y0 = int(x), int(y)
        x1 = x0 + max(1, int(width)) - 1
        y1 = y0 + max(1, int(height)) - 1
        draw.rectangle((x0, y0, x1, y1), outline="white", width=3)
        preview.save(PREVIEW_FILE, format="PNG")
        return True
    except Exception:
        return False


def main() -> int:
    print("=== Ozon C20 local solver evaluator ===")
    print("NO network. NO browser. NO CAPTCHA submission.")
    print(f"Capture dir: {CAPTURE_DIR}")

    images = _discover_images()
    if not images:
        report = {
            "goal": "evaluate_local_slider_solver_on_c20_capture",
            "gate": "OZON_C20_NO_DECODABLE_LOCAL_IMAGES",
            "capture_dir_exists": CAPTURE_DIR.exists(),
            "image_count": 0,
            "network_used": False,
            "captcha_submitted": False,
        }
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("[EVIDENCE] OZON_C20_NO_DECODABLE_LOCAL_IMAGES")
        return 8

    print(f"Decoded local images: {len(images)}")
    for image in images:
        print(
            f"  {image.path.name}: {image.width}x{image.height} mode={image.mode} "
            f"alpha={image.has_alpha} transparent={image.alpha_transparent_fraction:.3f}"
        )

    contour_results = _run_contour(images)
    difference_results = _run_difference(images)
    all_results = contour_results + difference_results
    successful = _successful(all_results)
    best = successful[0] if successful else None
    preview_written = bool(best and _write_preview(best, images))

    if best is not None:
        gate = "OZON_C20_LOCAL_SOLVER_RESULT_AVAILABLE"
    elif all_results:
        gate = "OZON_C20_LOCAL_IMAGES_PRESENT_SOLVER_FAIL_CLOSED"
    else:
        gate = "OZON_C20_IMAGES_NOT_PAIRABLE_FOR_CURRENT_SOLVER"

    report = {
        "goal": "evaluate_local_slider_solver_on_c20_capture",
        "gate": gate,
        "images": [image.safe_dict() for image in images],
        "piece_candidate_count": len(_piece_candidates(images)),
        "contour_attempt_count": len(contour_results),
        "difference_attempt_count": len(difference_results),
        "successful_result_count": len(successful),
        "best": best,
        "preview_written": preview_written,
        "preview_file": PREVIEW_FILE.name if preview_written else None,
        "network_used": False,
        "browser_used": False,
        "captcha_submitted": False,
    }
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SAFE RESULT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Report: {REPORT_FILE}")
    if preview_written:
        print(f"[INFO] Preview: {PREVIEW_FILE}")
    print(f"[EVIDENCE] {gate}")

    return 0 if best is not None else 8


if __name__ == "__main__":
    raise SystemExit(main())
