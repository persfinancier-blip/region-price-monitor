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

# Recovered ASocks-style forms described by Claude.
_SESSION_TAIL = re.compile(r"-hold-session-session-[A-Za-z0-9]+$", re.IGNORECASE)
_HOLD_QUERY_TAIL = re.compile(r"-hold-query(?:-[A-Za-z0-9]+)?$", re.IGNORECASE)
_HOLD_SESSION_TAIL = re.compile(r"-hold-session(?:-session)?$", re.IGNORECASE)

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
    """Rotate a proxy login to exactly one ``hold-session-session-<id>`` suffix.

    Recovered/required input forms:
    - bare login;
    - ``...-hold-query`` (or ``...-hold-query-<old>``);
    - already bound ``...-hold-session-session-<old>``.

    Older ``...-hold-session`` / ``...-hold-session-session`` forms are also
    accepted so the selector is backward compatible with earlier test data.
    """
    source = username.strip()
    if not source:
        raise ValueError("proxy username is required")
    sid = (session_id or secrets.token_hex(7)).strip()
    if not re.fullmatch(r"[A-Za-z0-9]+", sid):
        raise ValueError("session id must be alphanumeric")

    if _SESSION_TAIL.search(source):
        base = _SESSION_TAIL.sub("", source)
    elif _HOLD_QUERY_TAIL.search(source):
        base = _HOLD_QUERY_TAIL.sub("", source)
    elif _HOLD_SESSION_TAIL.search(source):
        base = _HOLD_SESSION_TAIL.sub("", source)
    else:
        base = source
    return f"{base}-hold-session-session-{sid}", sid


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
    evidence = {
        field: payload.get(field)
        for field in _OPERATOR_FIELDS
        if payload.get(field) not in (None, "")
    }
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


def _parse_combined_proxy(raw: str) -> tuple[str, str, str]:
    """Parse Claude CLI form: host:port:user:pass or scheme://host:port:user:pass."""
    value = raw.strip()
    if not value:
        raise ValueError("proxy is empty")
    scheme = "https"
    rest = value
    if "://" in value:
        scheme, rest = value.split("://", 1)
    parts = rest.split(":", 3)
    if len(parts) != 4:
        raise ValueError("proxy must be host:port:user:pass or scheme://host:port:user:pass")
    host, port, user, password = parts
    if not host or not port or not user or not password:
        raise ValueError("proxy fields cannot be blank")
    return f"{scheme}://{host}:{port}", user, password


def find_mobile_proxy(
    *,
    proxy_server: str,
    proxy_user: str,
    proxy_password: str,
    tries: int = 15,
    city_label: str = "mobile",
    verbose: bool = True,
) -> dict[str, Any]:
    """Rotate sticky sessions and stop on a known Russian mobile operator."""
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

        if verbose:
            print(f"[{index:02d}/{tries}] session={session_id} -> checking IP/operator ...", flush=True)

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

        accepted = bool(outcome.ok and payload and mobile_flag is True and operator)
        item = {
            "attempt": index,
            "session_id": session_id,
            "transport": transport,
            "proxy_auth_failed": auth_failed,
            "identity": identity,
            "operator": operator,
            "operator_fields": operator_fields,
            "accepted": accepted,
        }
        attempts.append(item)

        if verbose:
            if auth_failed:
                print("    AUTH FAILED (407/proxy authentication)", flush=True)
            elif not outcome.ok:
                print(
                    f"    transport failed: status={transport.get('status_code')} "
                    f"message={transport.get('message')}",
                    flush=True,
                )
            elif payload is None:
                print("    IP check returned non-JSON", flush=True)
            else:
                print(
                    "    "
                    f"ip={identity.get('query')} city={identity.get('city')} "
                    f"mobile={identity.get('mobile')} operator={operator or 'UNKNOWN'}",
                    flush=True,
                )

        if auth_failed:
            break
        if accepted:
            selected = {
                "attempt": index,
                "session_id": session_id,
                "identity": identity,
                "operator": operator,
                "proxy_context": context.safe_identity,
            }
            if verbose:
                print(f"    SELECTED: {operator} / {identity.get('query')}", flush=True)
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
        "goal": "reproduce_claude_sticky_mobile_proxy_selector_exactly",
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Claude recovered sticky mobile selector: rotate session id and stop on RU mobile operator."
    )
    parser.add_argument("--proxy", help="host:port:user:pass or scheme://host:port:user:pass")
    parser.add_argument("--tries", type=int, default=15)
    parser.add_argument("--city", default="mobile")
    parser.add_argument("--sku", help="accepted for compatibility with the recovered CLI; not used by selector-only C18")
    parser.add_argument("--cookies", help="accepted for compatibility with the recovered CLI; not used by selector-only C18")
    args = parser.parse_args()

    print("=== Claude sticky mobile proxy test C18 ===")
    print("rotate hold-session-session-<id> -> curl_cffi -> detect MTS/Beeline/MegaFon/Tele2/T2/Yota")
    print("NO Playwright. NO browser. Password input is VISIBLE.")
    print("Credentials are used in memory only and are NOT written to SAFE REPORT.")

    try:
        proxy_raw = args.proxy
        if not proxy_raw:
            proxy_raw = input("Proxy (VISIBLE host:port:user:pass): ").strip()
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(proxy_raw)
        report = find_mobile_proxy(
            proxy_server=proxy_server,
            proxy_user=proxy_user,
            proxy_password=proxy_password,
            tries=args.tries,
            city_label=args.city,
            verbose=True,
        )
    except Exception as exc:
        print(f"[ERROR] MOBILE_PROXY_SELECTOR_FAILED: {type(exc).__name__}: {exc}")
        return 2

    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report saved to: {REPORT_FILE}")
    print("[INFO] Password/login are not persisted. Session ids and public egress metadata are reported.")
    print(f"[EVIDENCE] {report['gate']}")
    return 0 if report["gate"] == "OZON_STICKY_MOBILE_OPERATOR_SELECTED" else 8


if __name__ == "__main__":
    raise SystemExit(main())
