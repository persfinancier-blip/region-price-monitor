from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
LOCAL = CORE / "local" / "probes"
C19_DIR = LOCAL / "ozon_same_sticky_direct_c19"
C20_DIR = LOCAL / "ozon_challenge_c20"
REPORT = LOCAL / "ozon_captcha_protocol_c21_report.json"

PROTOCOL_MARKERS = (
    "/abt/captcha/result",
    "/abt/captcha/ok",
    "/abt/captcha/fail",
    "application/json;charset=UTF-8",
    "Content-Encoding",
    "gzip",
    "credentials",
    "abt_att",
    "origin_referer",
    "captchaDone",
    "atob",
    "getQueryParams",
    "#image",
    "#puzzle",
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _b64decode(text: str) -> bytes | None:
    raw = text.strip()
    if not raw:
        return None
    raw = raw.replace("-", "+").replace("_", "/")
    raw += "=" * ((4 - len(raw) % 4) % 4)
    try:
        return base64.b64decode(raw, validate=False)
    except Exception:
        return None


def _raw_query(url: str) -> list[tuple[str, str]]:
    query = urlsplit(url).query
    out: list[tuple[str, str]] = []
    for item in query.split("&"):
        if not item:
            continue
        key, sep, value = item.partition("=")
        out.append((unquote(key), unquote(value) if sep else ""))
    return out


def _decode_captcha_structure(value: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "value_length": len(value),
        "value_sha256": _sha(value),
        "structured": False,
    }
    # The live client strips a short opaque prefix before Base64. Discover it
    # structurally instead of persisting or assuming the concrete prefix.
    for cut in range(0, min(12, len(value))):
        decoded = _b64decode(value[cut:])
        if not decoded:
            continue
        try:
            text = decoded.decode("utf-8")
        except UnicodeDecodeError:
            continue
        parts = text.split(",", 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[2].startswith("cp:"):
            continue
        token_parts = parts[2].split(":")
        inner_keys: list[str] = []
        inner_type: str | None = None
        if len(token_parts) >= 2:
            inner = _b64decode(token_parts[-1])
            if inner:
                try:
                    obj = json.loads(inner.decode("utf-8"))
                    inner_type = type(obj).__name__
                    if isinstance(obj, dict):
                        inner_keys = sorted(str(k) for k in obj.keys())
                except Exception:
                    pass
        result.update(
            {
                "structured": True,
                "opaque_prefix_length": cut,
                "outer_field_count": 3,
                "outer_field_lengths": [len(parts[0]), len(parts[1]), len(parts[2])],
                "token_segment_count": len(token_parts),
                "inner_decoded_type": inner_type,
                "inner_json_keys": inner_keys,
            }
        )
        return result
    return result


def _find_chrome() -> Path | None:
    candidate = C19_DIR / "chrome.txt"
    if candidate.exists():
        return candidate
    matches = sorted(C19_DIR.glob("*.txt")) if C19_DIR.exists() else []
    return matches[0] if matches else None


def _inspect_js() -> dict[str, Any]:
    files = sorted(C20_DIR.glob("*")) if C20_DIR.exists() else []
    evidence: dict[str, Any] = {"files_seen": len(files), "markers": {}}
    joined = ""
    for path in files:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            joined += "\n" + path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    for marker in PROTOCOL_MARKERS:
        evidence["markers"][marker] = marker in joined
    evidence["network_used"] = False
    return evidence


def main() -> int:
    LOCAL.mkdir(parents=True, exist_ok=True)
    chrome = _find_chrome()
    if chrome is None:
        report = {"goal": "local_ozon_captcha_protocol_analysis", "gate": "OZON_CAPTCHA_C19_EVIDENCE_MISSING"}
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 8

    try:
        challenge = json.loads(chrome.read_text(encoding="utf-8"))
    except Exception as exc:
        report = {
            "goal": "local_ozon_captcha_protocol_analysis",
            "gate": "OZON_CAPTCHA_C19_JSON_INVALID",
            "error_type": type(exc).__name__,
        }
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 8

    captcha_url = challenge.get("captchaURL")
    if not isinstance(captcha_url, str) or not captcha_url:
        report = {"goal": "local_ozon_captcha_protocol_analysis", "gate": "OZON_CAPTCHA_URL_MISSING"}
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 8

    params = _raw_query(captcha_url)
    param_meta: list[dict[str, Any]] = []
    structured = False
    for key, value in params:
        item: dict[str, Any] = {"name": key, "length": len(value), "sha256": _sha(value)}
        if key == "captcha":
            item["decode"] = _decode_captcha_structure(value)
            structured = bool(item["decode"].get("structured"))
        param_meta.append(item)

    js = _inspect_js()
    gate = "OZON_CAPTCHA_QUERY_PAYLOAD_STRUCTURED" if structured else "OZON_CAPTCHA_QUERY_STRUCTURE_CAPTURED"
    report = {
        "goal": "local_ozon_captcha_protocol_analysis",
        "challenge_top_level_keys": sorted(str(k) for k in challenge.keys()),
        "captcha_url": {
            "scheme": urlsplit(captcha_url).scheme,
            "host": urlsplit(captcha_url).hostname,
            "path_suffix": Path(urlsplit(captcha_url).path).suffix.lower() or None,
            "full_url_persisted": False,
        },
        "query_parameters": param_meta,
        "js_protocol": js,
        "full_query_values_persisted": False,
        "network_used": False,
        "gate": gate,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== SAFE C21 REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[EVIDENCE] {gate}")
    return 0 if structured else 8


if __name__ == "__main__":
    raise SystemExit(main())
