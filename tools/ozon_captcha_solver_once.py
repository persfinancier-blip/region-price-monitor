from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from captcha.ozon_payload import decode_captcha_url
from captcha.slider import solve_piece_by_contour
from mobile_proxy import _parse_combined_proxy, find_mobile_proxy
from probe_ozon_single_run_c23 import _fetch_bytes, _image_meta, _selected_context
from probe_ozon_solver_robustness_c24 import _make_preview, _obtain_challenge

DEFAULT_SKU = "3129447770"
OUT_ROOT = CORE / "local" / "probes" / "ozon_captcha_solver_once"
REPORT = OUT_ROOT / "solver_result.json"


def _safe_result(result: dict[str, Any]) -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SOLVER RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[INFO] Local result: {REPORT}")


def main() -> int:
    print("=== Ozon CAPTCHA solver-only ===")
    print("Gets live challenge -> fetches images -> computes x/y.")
    print("NO drag. NO submit. NO browser.")

    proxy_raw = input("Proxy (VISIBLE host:port:user:pass): ").strip()
    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU

    try:
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(proxy_raw)
    except Exception as exc:
        print(f"[ERROR] PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    selector = find_mobile_proxy(
        proxy_server=proxy_server,
        proxy_user=proxy_user,
        proxy_password=proxy_password,
        tries=15,
        city_label="ozon-solver-only",
        verbose=True,
    )
    selected = selector.get("selected")
    if not isinstance(selected, dict):
        _safe_result({"status": "blocked", "gate": selector.get("gate")})
        return 8

    context, session_id, selected_ip = _selected_context(
        proxy_server, proxy_user, proxy_password, selected
    )
    challenge, challenge_url, strategy, attempts, data_access = _obtain_challenge(context, sku)

    if data_access is not None:
        _safe_result({
            "status": "data_access_without_challenge",
            "sku": sku,
            "session_id": session_id,
            "selected_ip": selected_ip,
            "operator": selected.get("operator"),
            "strategy": strategy,
        })
        return 0

    if not isinstance(challenge, dict) or not challenge_url:
        _safe_result({
            "status": "challenge_not_obtained",
            "sku": sku,
            "session_id": session_id,
            "selected_ip": selected_ip,
            "operator": selected.get("operator"),
            "attempts": attempts,
        })
        return 8

    decoded = decode_captcha_url(challenge_url)
    background, bg_transport = _fetch_bytes(context, decoded.image_url)
    puzzle, puzzle_transport = _fetch_bytes(context, decoded.puzzle_url)

    if not background or not puzzle:
        _safe_result({
            "status": "image_fetch_failed",
            "sku": sku,
            "session_id": session_id,
            "selected_ip": selected_ip,
            "operator": selected.get("operator"),
            "background_transport": bg_transport,
            "puzzle_transport": puzzle_transport,
        })
        return 8

    bg_path = OUT_ROOT / "background.png"
    puzzle_path = OUT_ROOT / "puzzle.png"
    preview_path = OUT_ROOT / "preview.png"
    bg_path.write_bytes(background)
    puzzle_path.write_bytes(puzzle)

    solved = solve_piece_by_contour(background, puzzle)
    preview_saved = _make_preview(background, puzzle, solved, preview_path)

    result = {
        "status": "solved" if solved.ok else "solver_uncertain",
        "sku": sku,
        "session_id": session_id,
        "selected_ip": selected_ip,
        "operator": selected.get("operator"),
        "strategy": strategy,
        "challenge_version": decoded.version,
        "background": _image_meta(background),
        "puzzle": _image_meta(puzzle),
        "x": solved.x,
        "y": solved.y,
        "score": solved.score,
        "confidence": solved.confidence,
        "solver_error": solved.error,
        "preview_saved": preview_saved,
        "challenge_submitted": False,
        "credentials_persisted": False,
        "full_urls_persisted": False,
    }
    _safe_result(result)

    if solved.ok:
        print(f"\nSOLVED x={solved.x} y={solved.y} confidence={solved.confidence}")
        return 0
    return 8


if __name__ == "__main__":
    raise SystemExit(main())
