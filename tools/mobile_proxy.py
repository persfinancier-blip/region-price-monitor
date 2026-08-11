from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import secrets
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from curl_transport import request_via_proxy as curl_request_via_proxy
from transport import ProxyContext, ProxyContextError

NEUTRAL_URL = "https://api.i.pn/json/"
LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
REPORT_FILE = LOCAL_PROBES / "ozon_mobile_proxy_selector_report.json"

_SESSION_TAIL = re.compile(r"-hold-session-session-[A-Za-z0-9]+$", re.IGNORECASE)
_HOLD_TAIL = re.compile(r"-hold-session(?:-session)?$", re.IGNORECASE)

_OPERATOR_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MTS", (" mts", "mts ", "mobile telesystems", "mobile telesystem", "мтс")),
    ("BEELINE", ("beeline", "vimpelcom", "vimpel-com", "вымпелком", "veon")),
    ("MEGAFON", ("megafon", "mega fon", "мегафон")),
    ("TELE2_T2", ("tele2", "tele 2", "t2 mobile", "t2 rt", "t2-mobile", "теле2", " т2")),
    ("YOTA", ("yota", "scartel", "скартел", "йота")),
)

_OPERATOR_FIELDS = (
    "isp",
    "org",
    "as",
    "asName",
    "asname",
    "operator",
    "carrier",
    "company",
    "network",
    "reverse",
)


def rotate_session(username: str, session_id: str | None = None) -> tuple[str, str]:
    """Return username with exactly one ASocks-style sticky session suffix.

    Supported inputs match the recovered Claude note:
    - bare login;
    - login ending in ``-hold-session`` / ``-hold-session-session``;
    - login already ending in ``-hold-session-session-<id>``.
    """
    source = username.strip()
    if not source:
        raise ValueError("proxy username is required")
    sid = (session_id or secrets.token_hex(7)).strip()
    if not re.fullmatch(r"[A-Za-z0-9]+", sid):
        raise ValueError("session id must be alphanumeric")

    if _SESSION_TAIL.search(source):
        base = _SESSION_TAIL.sub("", source)
        return f"{base}-hold-session-session-{sid}", sid
    if _HOLD_TAIL.search(source):
        base = _HOLD_TAIL.sub("", source)
        return f"{base}-hold-session-session-{sid}", sid
    return f"{source}-hold-session-session-{sid}", sid


def _decode_json(body: Any) -> dict[str, Any] | None:
    if body is None:
        return None
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)
    try:
        payload = json.loads(text.lstrip("\ufeff \t\r\n"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _operator_evidence(payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    evidence = {field: payload.get(field) for field in _OPERATOR_FIELDS if payload.get(field) not in (None, "")}
    haystack = " " + " ".join(str(value) for value in evidence.values()).lower() + " "
    for name, needles in _OPERATOR_PATTERNS:
        if any(needle in haystack for needle in needles):
            return name, evidence
    return None, evidence


def _identity(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": payload.get("query"),
        "countryCode": payload.get("countryCode"),
        "regionName": payload.get("regionName"),
        "city": payload.get("city"),
        "mobile": payload.get("mobile"),
        "type": payload.get("type"),
        "proxy": payload.get("proxy"),
        "hosting": payload.get("hosting"),
    }


def _transport_auth_failed(transport: dict[str, Any]) -> bool:
    status = transport.get("status_code")
    text = " ".join(
        str(transport.get(key) or "")
        for key in ("message", "adapter_detail", "error", "detail")
    ).lower()
    return (
        status == 407
        or "proxy authentication required" in text
        or "proxy authentication" in text
        or ("407" in text and "proxy" in text)
    )


def find_mobile_proxy(
    *,
    proxy_server: str,
    proxy_user: str,
    proxy_password: str,
    tries: int = 15,
    city_label: str = "mobile",
) -> dict[str, Any]:
    if tries < 1 or tries > 100:
        raise ValueError("tries must be between 1 and 100")
    attempts: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None

    for index in range(1, tries + 1):
        rotated_user, session_id = rotate_session(proxy_user)
        try:
            context = ProxyContext.from_city(
                {
                    "city": city_label,
                    "proxy": proxy_server,
                    "proxy_user": rotated_user,
                    "proxy_password": proxy_password,
                },
                require_explicit_scheme=True,
            )
        except ProxyContextError as exc:
            raise ValueError(str(exc)) from exc

        outcome = curl_request_via_proxy(
            context,
            "GET",
            NEUTRAL_URL,
            impersonate="chrome",
            timeout=30,
            allow_redirects=True,
        )
        transport = outcome.safe_dict()
        payload = _decode_json(outcome.body) if outcome.ok else None
        identity = _identity(payload) if payload else None
        operator, operator_fields = _operator_evidence(payload) if payload else (None, {})
        mobile_flag = payload.get("mobile") if payload else None
        auth_failed = _transport_auth_failed(transport)

        item = {
            "attempt": index,
            "session_id": session_id,
            "transport": transport,
            "proxy_auth_failed": auth_failed,
            "identity": identity,
            "operator": operator,
            "operator_fields": operator_fields,
            "accepted": bool(outcome.ok and payload and mobile_flag is True and operator),
        }
        attempts.append(item)
        if auth_failed:
            break
        if item["accepted"]:
            selected = {
                "attempt": index,
                "session_id": session_id,
                "identity": identity,
                "operator": operator,
                "proxy_context": context.safe_identity,
            }
            break

    if selected:
        gate = "OZON_STICKY_MOBILE_OPERATOR_SELECTED"
    elif any(a.get("proxy_auth_failed") for a in attempts):
        gate = "OZON_STICKY_PROXY_AUTH_FAILED"
    elif any(a.get("identity", {}).get("mobile") is True for a in attempts if a.get("identity")):
        gate = "OZON_MOBILE_FLAG_SEEN_OPERATOR_UNPROVEN"
    elif any(a.get("transport", {}).get("ok") for a in attempts):
        gate = "OZON_STICKY_MOBILE_OPERATOR_NOT_FOUND"
    else:
        gate = "OZON_STICKY_PROXY_TRANSPORT_FAILED"

    return {
        "goal": "reproduce_recovered_sticky_mobile_proxy_selector",
        "neutral_url": NEUTRAL_URL,
        "tries_requested": tries,
        "proxy_context": f"{city_label}@{proxy_server}",
        "rotation_contract": "hold-session-session-<id>",
        "accepted_operators": [name for name, _ in _OPERATOR_PATTERNS],
        "attempts": attempts,
        "selected": selected,
        "credentials_persisted": False,
        "gate": gate,
    }


def _parse_combined_proxy(raw: str) -> tuple[str, str, str]:
    value = raw.strip()
    if not value:
        raise ValueError("proxy is empty")
    scheme = "https"
    rest = value
    if "://" in value:
        scheme, rest = value.split("://", 1)
    parts = rest.split(":")
    if len(parts) != 4:
        raise ValueError("combined --proxy must be host:port:user:pass or scheme://host:port:user:pass")
    host, port, user, password = parts
    if not host or not port or not user or not password:
        raise ValueError("combined proxy fields cannot be blank")
    return f"{scheme}://{host}:{port}", user, password


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rotate sticky mobile proxy session IDs and stop on a known RU mobile operator."
    )
    parser.add_argument("--proxy", help="host:port:user:pass or scheme://host:port:user:pass")
    parser.add_argument("--tries", type=int, default=15)
    parser.add_argument("--city", default="mobile")
    args = parser.parse_args()

    print("=== Recovered sticky mobile proxy selector C16 ===")
    print("Rotate hold-session-session-<id> -> curl_cffi IP/operator check -> stop on mobile operator.")
    print("No Playwright. No Ozon request. No cookies. No browser.")
    print("Diagnostic mode: proxy password input is VISIBLE but is never written to the SAFE REPORT.")

    try:
        if args.proxy:
            proxy_server, proxy_user, proxy_password = _parse_combined_proxy(args.proxy)
        else:
            proxy_server = input("Proxy address (REQUIRED scheme://host:port): ").strip()
            proxy_user = input("Proxy username: ").strip()
            proxy_password = input("Proxy password (VISIBLE, not saved): ").strip()
        report = find_mobile_proxy(
            proxy_server=proxy_server,
            proxy_user=proxy_user,
            proxy_password=proxy_password,
            tries=args.tries,
            city_label=args.city,
        )
    except Exception as exc:
        print(f"[ERROR] MOBILE_PROXY_SELECTOR_FAILED: {type(exc).__name__}: {exc}")
        return 2

    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Proxy username/password are not persisted. Only generated sticky session ids and public egress metadata are reported.")
    print(f"[EVIDENCE] {report['gate']}")
    return 0 if report["gate"] == "OZON_STICKY_MOBILE_OPERATOR_SELECTED" else 8


if __name__ == "__main__":
    raise SystemExit(main())
