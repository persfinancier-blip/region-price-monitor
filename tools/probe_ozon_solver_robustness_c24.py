from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from PIL import Image, ImageDraw
from curl_cffi import requests as creq

from captcha.ozon_payload import OzonEmbeddedChallengeError, decode_captcha_url
from captcha.slider import solve_piece_by_contour
from curl_transport import request_via_proxy as curl_request_via_proxy
from mobile_proxy import _decode_json, _parse_combined_proxy, _transport_auth_failed, find_mobile_proxy
from probe_ozon_reference_entrypoint import (
    API_URL,
    DEFAULT_IMPERSONATE,
    DEFAULT_SKU,
    O3_HEADERS,
    _body_text,
    _parse_exact_price,
)
from probe_ozon_single_run_c23 import _challenge_url, _fetch_bytes, _image_meta, _selected_context

LOCAL = CORE / "local" / "probes"
OUT_DIR = LOCAL / "ozon_solver_robustness_c24"
REPORT_FILE = LOCAL / "ozon_solver_robustness_c24_report.json"
NEUTRAL_URL = "https://api.i.pn/json/"


def _safe_write_report(report: dict[str, Any]) -> None:
    LOCAL.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[INFO] Safe report: {REPORT_FILE}")
    print(f"[EVIDENCE] {report['gate']}")


def _neutral_identity(context) -> tuple[str | None, dict[str, Any], str | None]:
    outcome = curl_request_via_proxy(
        context,
        "GET",
        NEUTRAL_URL,
        impersonate="chrome",
        timeout=30,
        allow_redirects=True,
    )
    safe = outcome.safe_dict()
    if _transport_auth_failed(safe):
        return None, safe, "proxy_auth_failed"
    if not outcome.ok:
        return None, safe, "proxy_transport_failed"
    payload = _decode_json(outcome.body)
    if payload is None:
        return None, safe, "neutral_non_json"
    ip = str(payload.get("query") or "").strip() or None
    return ip, safe, None if ip else "neutral_ip_missing"


def _make_preview(background: bytes, piece: bytes, solved, path: Path) -> bool:
    if not solved.ok or solved.x is None or solved.y is None:
        return False
    with Image.open(BytesIO(background)) as bg_img, Image.open(BytesIO(piece)) as piece_img:
        bg = bg_img.convert("RGBA")
        movable = piece_img.convert("RGBA")
        alpha_bbox = movable.getchannel("A").getbbox()
        if alpha_bbox is None:
            return False
        movable = movable.crop(alpha_bbox)
        x = int(solved.x)
        y = int(solved.y)
        preview = bg.copy()
        preview.alpha_composite(movable, (x, y))
        draw = ImageDraw.Draw(preview)
        draw.rectangle(
            (x, y, x + movable.width - 1, y + movable.height - 1),
            outline=(255, 0, 0, 255),
            width=2,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        preview.save(path, format="PNG")
    return True


def _classify_batch(results: list[dict[str, Any]], requested: int) -> str:
    solved = [r for r in results if r.get("outcome") == "solved" and r.get("continuity_ok") is True]
    if len(solved) == requested and requested > 0:
        return "OZON_SOLVER_ROBUSTNESS_PASS"
    if solved:
        return "OZON_SOLVER_ROBUSTNESS_PARTIAL"
    return "OZON_SOLVER_ROBUSTNESS_BLOCKED"


def _obtain_challenge(context, sku: str) -> tuple[dict[str, Any] | None, str | None, str | None, list[dict[str, Any]], dict[str, Any] | None]:
    headers = dict(O3_HEADERS)
    headers["Referer"] = f"https://www.ozon.ru/product/{sku}/"
    attempts: list[dict[str, Any]] = []

    for strategy in DEFAULT_IMPERSONATE:
        outcome = curl_request_via_proxy(
            context,
            "GET",
            API_URL,
            client=creq,
            params={"url": f"/product/{sku}/"},
            headers=headers,
            impersonate=strategy,
            timeout=45,
            allow_redirects=True,
        )
        text = _body_text(outcome.body)
        payload = _decode_json(outcome.body) if outcome.ok or text else None
        url = _challenge_url(payload)
        parsed = _parse_exact_price(payload, sku) if isinstance(payload, dict) else None
        attempts.append(
            {
                "strategy": strategy,
                "transport": outcome.safe_dict(),
                "json_decoded": isinstance(payload, dict),
                "captcha_url_present": bool(url),
                "top_level_keys": sorted(payload.keys())[:80] if isinstance(payload, dict) else None,
                "exact_product": parsed,
            }
        )
        if url and isinstance(payload, dict):
            return payload, url, strategy, attempts, None
        if parsed and parsed.get("ok"):
            return None, None, strategy, attempts, parsed

    return None, None, None, attempts, None


def _run_once(index: int, *, proxy_server: str, proxy_user: str, proxy_password: str, sku: str) -> dict[str, Any]:
    run_dir = OUT_DIR / f"run_{index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n--- C24 run {index} ---")
    selector = find_mobile_proxy(
        proxy_server=proxy_server,
        proxy_user=proxy_user,
        proxy_password=proxy_password,
        tries=15,
        city_label=f"ozon-c24-{index}",
        verbose=True,
    )
    selected = selector.get("selected")
    if not isinstance(selected, dict):
        return {
            "run": index,
            "outcome": "blocked",
            "gate": "MOBILE_PROXY_NOT_SELECTED",
            "selector_gate": selector.get("gate"),
            "attempt_count": len(selector.get("attempts") or []),
            "continuity_ok": False,
        }

    try:
        context, session_id, selected_ip = _selected_context(
            proxy_server,
            proxy_user,
            proxy_password,
            selected,
        )
    except Exception as exc:
        return {
            "run": index,
            "outcome": "blocked",
            "gate": "PROXY_CONTEXT_INVALID",
            "operator": selected.get("operator"),
            "error_type": type(exc).__name__,
            "continuity_ok": False,
        }

    pre_ip, pre_transport, pre_error = _neutral_identity(context)
    if pre_error or pre_ip != selected_ip:
        return {
            "run": index,
            "outcome": "blocked",
            "gate": "PRE_CHALLENGE_STICKY_IP_MISMATCH" if pre_ip != selected_ip else "PRE_CHALLENGE_TRANSPORT_FAILED",
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "pre_ip": pre_ip,
            "pre_transport": pre_transport,
            "continuity_ok": False,
        }

    challenge, challenge_url, strategy, attempts, data_access = _obtain_challenge(context, sku)
    if data_access is not None:
        return {
            "run": index,
            "outcome": "data_access_without_challenge",
            "gate": "ZERO_COOKIE_DATA_ACCESS_PROVEN",
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "pre_ip": pre_ip,
            "entrypoint_attempts": attempts,
            "continuity_ok": True,
        }
    if not isinstance(challenge, dict) or not challenge_url:
        return {
            "run": index,
            "outcome": "blocked",
            "gate": "CHALLENGE_NOT_OBTAINED",
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "pre_ip": pre_ip,
            "entrypoint_attempts": attempts,
            "continuity_ok": True,
        }

    (run_dir / "challenge.json").write_text(json.dumps(challenge, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        embedded = decode_captcha_url(challenge_url)
    except OzonEmbeddedChallengeError as exc:
        return {
            "run": index,
            "outcome": "blocked",
            "gate": "CHALLENGE_PAYLOAD_INVALID",
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "pre_ip": pre_ip,
            "challenge_strategy": strategy,
            "error_type": type(exc).__name__,
            "continuity_ok": True,
        }

    bg_bytes, bg_transport = _fetch_bytes(context, embedded.image_url)
    piece_bytes, piece_transport = _fetch_bytes(context, embedded.puzzle_url)
    if (
        bg_transport.get("proxy_auth_failed")
        or piece_transport.get("proxy_auth_failed")
        or not bg_transport.get("ok")
        or not piece_transport.get("ok")
        or not bg_bytes
        or not piece_bytes
    ):
        return {
            "run": index,
            "outcome": "blocked",
            "gate": "IMAGE_FETCH_FAILED",
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "pre_ip": pre_ip,
            "challenge_strategy": strategy,
            "payload": embedded.safe_dict(),
            "background_transport": bg_transport,
            "puzzle_transport": piece_transport,
            "continuity_ok": True,
        }

    try:
        bg_meta = _image_meta(bg_bytes)
        piece_meta = _image_meta(piece_bytes)
    except Exception as exc:
        return {
            "run": index,
            "outcome": "blocked",
            "gate": "IMAGE_BYTES_INVALID",
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "pre_ip": pre_ip,
            "challenge_strategy": strategy,
            "payload": embedded.safe_dict(),
            "error_type": type(exc).__name__,
            "continuity_ok": True,
        }

    (run_dir / "background.png").write_bytes(bg_bytes)
    (run_dir / "puzzle.png").write_bytes(piece_bytes)

    solved = solve_piece_by_contour(piece_bytes, bg_bytes)
    preview_saved = _make_preview(bg_bytes, piece_bytes, solved, run_dir / "preview.png")

    post_ip, post_transport, post_error = _neutral_identity(context)
    continuity_ok = not post_error and post_ip == selected_ip

    return {
        "run": index,
        "outcome": "solved" if solved.ok else "solver_uncertain",
        "gate": "SOLVED" if solved.ok else "SOLVER_UNCERTAIN",
        "session_id": session_id,
        "operator": selected.get("operator"),
        "selected_ip": selected_ip,
        "pre_ip": pre_ip,
        "post_ip": post_ip,
        "continuity_ok": continuity_ok,
        "post_transport": post_transport,
        "challenge_strategy": strategy,
        "payload": embedded.safe_dict(),
        "background": {"image": bg_meta, "transport": bg_transport},
        "puzzle": {"image": piece_meta, "transport": piece_transport},
        "solver": solved.safe_dict(),
        "preview_saved": preview_saved,
        "local_dir": run_dir.name,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repeat fresh live Ozon challenge image solves without submission.")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args(argv)
    if args.runs < 1 or args.runs > 5:
        print("[ERROR] --runs must be between 1 and 5")
        return 2

    print("=== Ozon solver robustness C24 ===")
    print("fresh sticky -> challenge -> images -> local solver, repeated in one operator invocation")
    print("NO CAPTCHA submission. NO browser. NO external solver service.")

    proxy_raw = input("Proxy (VISIBLE host:port:user:pass): ").strip()
    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU
    try:
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(proxy_raw)
    except Exception as exc:
        _safe_write_report({
            "goal": "validate_live_ozon_solver_robustness",
            "requested_runs": args.runs,
            "error_type": type(exc).__name__,
            "gate": "OZON_SOLVER_ROBUSTNESS_PROXY_INVALID",
            "credentials_persisted": False,
            "full_urls_persisted": False,
            "challenge_submitted": False,
        })
        return 8

    results: list[dict[str, Any]] = []
    for index in range(1, args.runs + 1):
        result = _run_once(
            index,
            proxy_server=proxy_server,
            proxy_user=proxy_user,
            proxy_password=proxy_password,
            sku=sku,
        )
        results.append(result)
        solver = result.get("solver") or {}
        print(
            f"[RUN {index}] outcome={result.get('outcome')} gate={result.get('gate')} "
            f"ip_ok={result.get('continuity_ok')} x={solver.get('x')} "
            f"confidence={solver.get('confidence')}"
        )

    gate = _classify_batch(results, args.runs)
    solved_results = [r for r in results if r.get("outcome") == "solved" and r.get("continuity_ok") is True]
    confidences = [float((r.get("solver") or {}).get("confidence") or 0.0) for r in solved_results]
    summary = {
        "solved_count": len(solved_results),
        "requested_runs": args.runs,
        "confidence_min": min(confidences) if confidences else None,
        "confidence_max": max(confidences) if confidences else None,
        "confidence_mean": (sum(confidences) / len(confidences)) if confidences else None,
    }
    report = {
        "goal": "validate_live_ozon_solver_robustness",
        "sku": sku,
        "summary": summary,
        "runs": results,
        "raw_local_root": OUT_DIR.name,
        "credentials_persisted": False,
        "full_urls_persisted": False,
        "challenge_submitted": False,
        "browser_used": False,
        "external_solver_used": False,
        "gate": gate,
    }
    _safe_write_report(report)
    return 0 if gate == "OZON_SOLVER_ROBUSTNESS_PASS" else 8


if __name__ == "__main__":
    raise SystemExit(main())
