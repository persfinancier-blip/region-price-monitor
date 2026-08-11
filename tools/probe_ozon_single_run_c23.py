from __future__ import annotations

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

from PIL import Image
from curl_cffi import requests as creq

from captcha.ozon_payload import OzonEmbeddedChallengeError, decode_captcha_url
from captcha.slider import solve_piece_by_contour
from curl_transport import request_via_proxy as curl_request_via_proxy
from mobile_proxy import (
    _decode_json,
    _parse_combined_proxy,
    _transport_auth_failed,
    find_mobile_proxy,
    rotate_session,
)
from probe_ozon_reference_entrypoint import (
    API_URL,
    DEFAULT_IMPERSONATE,
    DEFAULT_SKU,
    O3_HEADERS,
    _body_text,
    _parse_exact_price,
)
from transport import ProxyContext

LOCAL = CORE / "local" / "probes"
OUT_DIR = LOCAL / "ozon_single_run_c23"
REPORT_FILE = LOCAL / "ozon_single_run_c23_report.json"
NEUTRAL_URL = "https://api.i.pn/json/"


def _challenge_url(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("captchaURL")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _proxy_url(context: ProxyContext) -> str:
    host = f"[{context.host}]" if ":" in context.host and not context.host.startswith("[") else context.host
    return f"{context.scheme}://{host}:{context.port}"


def _fetch_bytes(context: ProxyContext, url: str) -> tuple[bytes | None, dict[str, Any]]:
    try:
        response = creq.get(
            url,
            proxy=_proxy_url(context),
            proxy_auth=(context.proxy_user, context.proxy_password),
            impersonate="chrome",
            timeout=40,
            allow_redirects=True,
            headers={
                "Referer": "https://www.ozon.ru/",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
    except Exception as exc:
        text = context.redact(str(exc))
        low = text.lower()
        return None, {
            "ok": False,
            "status_code": None,
            "proxy_auth_failed": "407" in low or ("proxy" in low and "auth" in low),
            "error_type": type(exc).__name__,
            "message": text,
        }

    body = bytes(response.content or b"")
    status = int(response.status_code)
    return body, {
        "ok": 200 <= status < 400,
        "status_code": status,
        "proxy_auth_failed": status == 407,
        "bytes": len(body),
        "content_type": str(response.headers.get("content-type") or "").split(";")[0].strip().lower() or None,
    }


def _image_meta(data: bytes) -> dict[str, Any]:
    with Image.open(BytesIO(data)) as image:
        image.load()
        return {
            "format": image.format,
            "width": int(image.width),
            "height": int(image.height),
            "mode": image.mode,
            "bytes": len(data),
        }


def _write_report(report: dict[str, Any]) -> None:
    LOCAL.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[INFO] Safe report: {REPORT_FILE}")
    print(f"[EVIDENCE] {report['gate']}")


def _selected_context(
    proxy_server: str,
    proxy_user: str,
    proxy_password: str,
    selected: dict[str, Any],
) -> tuple[ProxyContext, str, str]:
    session_id = str(selected.get("session_id") or "").strip()
    identity = selected.get("identity") or {}
    selected_ip = str(identity.get("query") or "").strip()
    if not session_id or not selected_ip:
        raise ValueError("selected mobile session/id missing")

    bound_user, actual_sid = rotate_session(proxy_user, session_id)
    if actual_sid != session_id:
        raise ValueError("selected sticky session id not preserved")

    context = ProxyContext.from_city(
        {
            "city": "ozon-c23",
            "proxy": proxy_server,
            "proxy_user": bound_user,
            "proxy_password": proxy_password,
        },
        require_explicit_scheme=True,
    )
    return context, session_id, selected_ip


def main() -> int:
    print("=== Ozon single-run mobile challenge solver C23 ===")
    print("fresh mobile sticky -> immediate Ozon challenge -> embedded images -> local solver")
    print("ONE process. NO historical C18/C19 IP dependency. NO CAPTCHA submission.")

    proxy_raw = input("Proxy (VISIBLE host:port:user:pass): ").strip()
    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU

    try:
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(proxy_raw)
    except Exception as exc:
        _write_report({
            "goal": "single_run_mobile_challenge_local_solve",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": "OZON_SINGLE_RUN_PROXY_CONTEXT_INVALID",
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    print("[1/5] Selecting a fresh Russian mobile sticky session ...", flush=True)
    selector = find_mobile_proxy(
        proxy_server=proxy_server,
        proxy_user=proxy_user,
        proxy_password=proxy_password,
        tries=15,
        city_label="ozon-c23",
        verbose=True,
    )
    selected = selector.get("selected")
    if not isinstance(selected, dict):
        _write_report({
            "goal": "single_run_mobile_challenge_local_solve",
            "selector_gate": selector.get("gate"),
            "attempt_count": len(selector.get("attempts") or []),
            "gate": "OZON_SINGLE_RUN_MOBILE_PROXY_NOT_SELECTED",
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    try:
        context, session_id, selected_ip = _selected_context(
            proxy_server,
            proxy_user,
            proxy_password,
            selected,
        )
    except Exception as exc:
        _write_report({
            "goal": "single_run_mobile_challenge_local_solve",
            "operator": selected.get("operator"),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": "OZON_SINGLE_RUN_PROXY_CONTEXT_INVALID",
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    print("[2/5] Immediately rechecking THIS run's selected sticky IP ...", flush=True)
    neutral = curl_request_via_proxy(
        context,
        "GET",
        NEUTRAL_URL,
        impersonate="chrome",
        timeout=30,
        allow_redirects=True,
    )
    neutral_safe = neutral.safe_dict()
    neutral_payload = _decode_json(neutral.body) if neutral.ok else None
    observed_ip = str((neutral_payload or {}).get("query") or "").strip() or None

    if _transport_auth_failed(neutral_safe):
        gate = "OZON_SINGLE_RUN_PROXY_AUTH_FAILED"
    elif not neutral.ok or neutral_payload is None:
        gate = "OZON_SINGLE_RUN_PROXY_TRANSPORT_FAILED"
    elif observed_ip != selected_ip:
        gate = "OZON_SINGLE_RUN_STICKY_IP_MISMATCH"
    else:
        gate = None

    if gate:
        _write_report({
            "goal": "single_run_mobile_challenge_local_solve",
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "observed_ip": observed_ip,
            "same_ip": observed_ip == selected_ip,
            "neutral_transport": neutral_safe,
            "gate": gate,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    print(f"      SAME CURRENT IP CONFIRMED: {observed_ip}")
    print("[3/5] Requesting live Ozon entrypoint challenge through SAME ProxyContext ...", flush=True)

    headers = dict(O3_HEADERS)
    headers["Referer"] = f"https://www.ozon.ru/product/{sku}/"
    attempts: list[dict[str, Any]] = []
    challenge_payload: dict[str, Any] | None = None
    challenge_url: str | None = None
    challenge_strategy: str | None = None
    data_access: dict[str, Any] | None = None

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
        attempts.append({
            "strategy": strategy,
            "transport": outcome.safe_dict(),
            "json_decoded": isinstance(payload, dict),
            "captcha_url_present": bool(url),
            "top_level_keys": sorted(payload.keys())[:80] if isinstance(payload, dict) else None,
            "exact_product": parsed,
        })
        print(
            f"      [{strategy}] status={outcome.status_code} json={isinstance(payload, dict)} "
            f"captchaURL={bool(url)} data={bool(parsed and parsed.get('ok'))}",
            flush=True,
        )
        if url and isinstance(payload, dict):
            challenge_payload = payload
            challenge_url = url
            challenge_strategy = strategy
            break
        if parsed and parsed.get("ok"):
            data_access = parsed
            break

    if data_access is not None:
        _write_report({
            "goal": "single_run_mobile_challenge_local_solve",
            "sku": sku,
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "observed_ip": observed_ip,
            "entrypoint_attempts": attempts,
            "data_access": data_access,
            "gate": "OZON_SINGLE_RUN_ZERO_COOKIE_DATA_ACCESS_PROVEN",
            "credentials_persisted": False,
            "full_urls_persisted": False,
            "challenge_submitted": False,
        })
        return 0

    if not challenge_url or not isinstance(challenge_payload, dict):
        _write_report({
            "goal": "single_run_mobile_challenge_local_solve",
            "sku": sku,
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "observed_ip": observed_ip,
            "entrypoint_attempts": attempts,
            "gate": "OZON_SINGLE_RUN_CHALLENGE_NOT_OBTAINED",
            "credentials_persisted": False,
            "full_urls_persisted": False,
            "challenge_submitted": False,
        })
        return 8

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "challenge.json").write_text(
        json.dumps(challenge_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("[4/5] Decoding embedded image URLs and fetching exact background/puzzle ...", flush=True)
    try:
        embedded = decode_captcha_url(challenge_url)
    except OzonEmbeddedChallengeError as exc:
        _write_report({
            "goal": "single_run_mobile_challenge_local_solve",
            "sku": sku,
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "challenge_strategy": challenge_strategy,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": "OZON_SINGLE_RUN_CHALLENGE_PAYLOAD_INVALID",
            "credentials_persisted": False,
            "full_urls_persisted": False,
            "challenge_submitted": False,
        })
        return 8

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
        _write_report({
            "goal": "single_run_mobile_challenge_local_solve",
            "sku": sku,
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "payload": embedded.safe_dict(),
            "background_transport": bg_transport,
            "puzzle_transport": piece_transport,
            "gate": "OZON_SINGLE_RUN_IMAGE_FETCH_FAILED",
            "credentials_persisted": False,
            "full_urls_persisted": False,
            "challenge_submitted": False,
        })
        return 8

    try:
        bg_meta = _image_meta(bg_bytes)
        piece_meta = _image_meta(piece_bytes)
    except Exception as exc:
        _write_report({
            "goal": "single_run_mobile_challenge_local_solve",
            "sku": sku,
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "payload": embedded.safe_dict(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": "OZON_SINGLE_RUN_IMAGE_BYTES_INVALID",
            "credentials_persisted": False,
            "full_urls_persisted": False,
            "challenge_submitted": False,
        })
        return 8

    (OUT_DIR / "background.bin").write_bytes(bg_bytes)
    (OUT_DIR / "puzzle.bin").write_bytes(piece_bytes)
    print(f"      background={bg_meta['width']}x{bg_meta['height']} {bg_meta['format']}")
    print(f"      puzzle={piece_meta['width']}x{piece_meta['height']} {piece_meta['format']}")

    print("[5/5] Running repository-owned contour solver on THIS live challenge ...", flush=True)
    solved = solve_piece_by_contour(piece_bytes, bg_bytes)
    print(
        f"      ok={solved.ok} x={solved.x} y={solved.y} "
        f"score={solved.score:.6f} confidence={solved.confidence:.6f} error={solved.error}"
    )

    gate = (
        "OZON_SINGLE_RUN_CHALLENGE_IMAGES_SOLVED_LOCAL"
        if solved.ok
        else "OZON_SINGLE_RUN_SOLVER_UNCERTAIN"
    )
    report = {
        "goal": "single_run_mobile_challenge_local_solve",
        "sku": sku,
        "session_id": session_id,
        "operator": selected.get("operator"),
        "selected_ip": selected_ip,
        "observed_ip": observed_ip,
        "same_ip": True,
        "challenge_strategy": challenge_strategy,
        "payload": embedded.safe_dict(),
        "background": {
            "transport": bg_transport,
            "image": bg_meta,
            "raw_persisted_local_only": True,
        },
        "puzzle": {
            "transport": piece_transport,
            "image": piece_meta,
            "raw_persisted_local_only": True,
        },
        "solver": solved.safe_dict(),
        "challenge_submitted": False,
        "browser_used": False,
        "external_solver_used": False,
        "credentials_persisted": False,
        "full_urls_persisted": False,
        "gate": gate,
    }
    _write_report(report)
    return 0 if solved.ok else 8


if __name__ == "__main__":
    raise SystemExit(main())
