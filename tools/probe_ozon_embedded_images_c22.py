from __future__ import annotations

import hashlib
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
from mobile_proxy import _parse_combined_proxy, _transport_auth_failed, rotate_session
from transport import ProxyContext

LOCAL = CORE / "local" / "probes"
C18_REPORT = LOCAL / "ozon_mobile_proxy_selector_report.json"
C19_DIR = LOCAL / "ozon_same_sticky_direct_c19"
OUT_DIR = LOCAL / "ozon_payload_c22"
REPORT_FILE = LOCAL / "ozon_payload_c22_report.json"
NEUTRAL_URL = "https://api.i.pn/json/"


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain object JSON")
    return value


def _load_c18() -> tuple[str, str, str | None]:
    data = _load_json(C18_REPORT)
    if data.get("gate") != "OZON_STICKY_MOBILE_OPERATOR_SELECTED":
        raise ValueError("C18 gate is not accepted")
    selected = data.get("selected") or {}
    sid = str(selected.get("session_id") or "").strip()
    identity = selected.get("identity") or {}
    ip = str(identity.get("query") or "").strip()
    operator = selected.get("operator")
    if not sid or not ip:
        raise ValueError("C18 selected session/IP missing")
    return sid, ip, str(operator) if operator else None


def _find_chrome() -> Path:
    path = C19_DIR / "chrome.txt"
    if path.exists():
        return path
    candidates = sorted(C19_DIR.glob("*.txt")) if C19_DIR.exists() else []
    if not candidates:
        raise ValueError("C19 raw challenge files missing")
    return candidates[0]


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
            headers={"Referer": "https://www.ozon.ru/", "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"},
        )
    except Exception as exc:
        text = context.redact(str(exc))
        low = text.lower()
        auth = "407" in low or ("proxy" in low and "auth" in low)
        return None, {
            "ok": False,
            "status_code": None,
            "proxy_auth_failed": auth,
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
            "sha256": _sha_bytes(data),
            "bytes": len(data),
        }


def _write_report(report: dict[str, Any]) -> None:
    LOCAL.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[INFO] Safe report: {REPORT_FILE}")
    print(f"[EVIDENCE] {report['gate']}")


def main() -> int:
    print("=== Ozon embedded challenge image solver C22 ===")
    print("C19 captchaURL -> local decode -> exact image URLs -> SAME sticky proxy -> local solver.")
    print("NO browser. NO external solver API. NO challenge submission.")

    try:
        sid, expected_ip, operator = _load_c18()
        chrome_path = _find_chrome()
        challenge = _load_json(chrome_path)
        captcha_url = challenge.get("captchaURL")
        payload = decode_captcha_url(captcha_url)
    except (OzonEmbeddedChallengeError, ValueError, OSError, json.JSONDecodeError) as exc:
        report = {
            "goal": "decode_embedded_ozon_images_and_solve_locally",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": "OZON_EMBEDDED_CHALLENGE_PAYLOAD_INVALID",
            "credentials_persisted": False,
            "full_urls_persisted": False,
        }
        _write_report(report)
        return 8

    print(f"Embedded payload decoded: version={payload.version} pp={list(payload.pp)}")
    print("Exact background/puzzle URLs recovered in memory; full URLs are not printed.")
    proxy_raw = input("Proxy (VISIBLE host:port:user:pass): ").strip()
    try:
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(proxy_raw)
        bound_user, actual_sid = rotate_session(proxy_user, sid)
        if actual_sid != sid:
            raise ValueError("exact C18 sticky session id not preserved")
        context = ProxyContext.from_city(
            {
                "city": "ozon-c22",
                "proxy": proxy_server,
                "proxy_user": bound_user,
                "proxy_password": proxy_password,
            },
            require_explicit_scheme=True,
        )
    except Exception as exc:
        report = {
            "goal": "decode_embedded_ozon_images_and_solve_locally",
            "payload": payload.safe_dict(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": "OZON_EMBEDDED_CHALLENGE_PROXY_CONTEXT_INVALID",
            "credentials_persisted": False,
            "full_urls_persisted": False,
        }
        _write_report(report)
        return 8

    print("[1/3] Rechecking exact C18 sticky public IP ...")
    neutral = curl_request_via_proxy(context, "GET", NEUTRAL_URL, impersonate="chrome", timeout=30, allow_redirects=True)
    neutral_safe = neutral.safe_dict()
    observed_ip = None
    if neutral.ok:
        try:
            obj = json.loads(str(neutral.body))
            if isinstance(obj, dict):
                observed_ip = str(obj.get("query") or "").strip() or None
        except Exception:
            pass

    if _transport_auth_failed(neutral_safe):
        gate = "OZON_EMBEDDED_CHALLENGE_PROXY_AUTH_FAILED"
    elif not neutral.ok:
        gate = "OZON_EMBEDDED_CHALLENGE_PROXY_TRANSPORT_FAILED"
    elif observed_ip != expected_ip:
        gate = "OZON_EMBEDDED_CHALLENGE_STICKY_IP_MISMATCH"
    else:
        gate = None

    if gate:
        report = {
            "goal": "decode_embedded_ozon_images_and_solve_locally",
            "payload": payload.safe_dict(),
            "sticky": {"operator": operator, "expected_ip": expected_ip, "observed_ip": observed_ip, "same_ip": observed_ip == expected_ip},
            "neutral_transport": neutral_safe,
            "gate": gate,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        }
        _write_report(report)
        return 8

    print(f"      SAME IP CONFIRMED: {observed_ip}")
    print("[2/3] Fetching exact embedded background + puzzle bytes through SAME proxy ...")
    bg_bytes, bg_transport = _fetch_bytes(context, payload.image_url)
    piece_bytes, piece_transport = _fetch_bytes(context, payload.puzzle_url)

    if bg_transport.get("proxy_auth_failed") or piece_transport.get("proxy_auth_failed"):
        gate = "OZON_EMBEDDED_CHALLENGE_PROXY_AUTH_FAILED"
    elif not bg_transport.get("ok") or not piece_transport.get("ok") or not bg_bytes or not piece_bytes:
        gate = "OZON_EMBEDDED_CHALLENGE_IMAGE_FETCH_FAILED"
    else:
        gate = None

    bg_meta = piece_meta = None
    if gate is None:
        try:
            bg_meta = _image_meta(bg_bytes)
            piece_meta = _image_meta(piece_bytes)
        except Exception as exc:
            gate = "OZON_EMBEDDED_CHALLENGE_IMAGE_BYTES_INVALID"
            image_error = f"{type(exc).__name__}: {exc}"
        else:
            image_error = None
    else:
        image_error = None

    if gate:
        report = {
            "goal": "decode_embedded_ozon_images_and_solve_locally",
            "payload": payload.safe_dict(),
            "sticky": {"operator": operator, "expected_ip": expected_ip, "observed_ip": observed_ip, "same_ip": True},
            "background_transport": bg_transport,
            "puzzle_transport": piece_transport,
            "image_error": image_error,
            "gate": gate,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        }
        _write_report(report)
        return 8

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "background.bin").write_bytes(bg_bytes)
    (OUT_DIR / "puzzle.bin").write_bytes(piece_bytes)
    print(f"      background={bg_meta['width']}x{bg_meta['height']} {bg_meta['format']}")
    print(f"      puzzle={piece_meta['width']}x{piece_meta['height']} {piece_meta['format']}")

    print("[3/3] Running repository-owned contour solver ...")
    solved = solve_piece_by_contour(piece_bytes, bg_bytes)
    print(f"      ok={solved.ok} x={solved.x} y={solved.y} score={solved.score:.6f} confidence={solved.confidence:.6f} error={solved.error}")
    gate = "OZON_EMBEDDED_CHALLENGE_IMAGES_SOLVED_LOCAL" if solved.ok else "OZON_EMBEDDED_CHALLENGE_IMAGES_CAPTURED_SOLVER_UNCERTAIN"

    report = {
        "goal": "decode_embedded_ozon_images_and_solve_locally",
        "payload": payload.safe_dict(),
        "sticky": {"operator": operator, "expected_ip": expected_ip, "observed_ip": observed_ip, "same_ip": True},
        "background": {"transport": bg_transport, "image": bg_meta, "raw_persisted_local_only": True},
        "puzzle": {"transport": piece_transport, "image": piece_meta, "raw_persisted_local_only": True},
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
