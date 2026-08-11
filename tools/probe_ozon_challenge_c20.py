from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from curl_transport import request_via_proxy as curl_request_via_proxy
from transport import ProxyContext
from mobile_proxy import _parse_combined_proxy, rotate_session

C18_REPORT = CORE / "local" / "probes" / "ozon_mobile_proxy_selector_report.json"
C19_RAW_DIR = CORE / "local" / "probes" / "ozon_same_sticky_direct_c19"
OUT_DIR = CORE / "local" / "probes" / "ozon_challenge_c20"
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_FILE = CORE / "local" / "probes" / "ozon_challenge_c20_report.json"
NEUTRAL_URL = "https://api.i.pn/json/"

CHALLENGE_URL_KEYS = ("captchaURL", "challengeURL", "blockURL")
_PROVIDER_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("GEETEST", ("geetest", "gt4", "captcha_id")),
    ("DATADOME", ("datadome", "geo.captcha-delivery")),
    ("HUMAN_PERIMETERX", ("perimeterx", "px-captcha", "humansecurity")),
    ("CLOUDFLARE", ("cloudflare", "turnstile", "cf-chl")),
    ("ARKOSE", ("arkoselabs", "funcaptcha", "arkose")),
    ("HCAPTCHA", ("hcaptcha",)),
    ("RECAPTCHA", ("recaptcha", "g-recaptcha")),
    ("SLIDER_PUZZLE_GENERIC", ("slider", "puzzle", "ползунк", "пазл")),
)

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
_URL_RE = re.compile(r"https?://[^\s\"'<>\\)]+", re.IGNORECASE)
_ATTR_URL_RE = re.compile(r"(?:src|href)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_CSS_URL_RE = re.compile(r"url\(\s*[\"']?([^\"')]+)", re.IGNORECASE)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _body_bytes(body: Any) -> bytes:
    if body is None:
        return b""
    if isinstance(body, bytes):
        return body
    return str(body).encode("utf-8", errors="replace")


def _body_text(body: Any) -> str:
    return _body_bytes(body).decode("utf-8", errors="replace")


def _json_dict(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text.lstrip("\ufeff \t\r\n"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _find_c19_challenge() -> tuple[dict[str, Any], Path] | None:
    if not C19_RAW_DIR.exists():
        return None
    for path in sorted(C19_RAW_DIR.glob("*.txt")):
        try:
            payload = _json_dict(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if payload and any(payload.get(key) for key in CHALLENGE_URL_KEYS):
            return payload, path
    return None


def _first_challenge_url(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in CHALLENGE_URL_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return key, value.strip()
    return None, None


def _safe_url_meta(raw_url: str | None) -> dict[str, Any] | None:
    if not raw_url:
        return None
    parsed = urlparse(raw_url)
    path = parsed.path or "/"
    return {
        "scheme": parsed.scheme or None,
        "host": parsed.hostname,
        "port": parsed.port,
        "path_depth": len([part for part in path.split("/") if part]),
        "path_suffix": Path(path).suffix.lower() or None,
        "query_present": bool(parsed.query),
        "full_url_persisted": False,
    }


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _fingerprint(text: str, payload: dict[str, Any] | None = None) -> list[str]:
    haystack = text.lower()
    if payload is not None:
        haystack += "\n" + "\n".join(_walk_strings(payload)).lower()
    found: list[str] = []
    for name, markers in _PROVIDER_MARKERS:
        if any(marker in haystack for marker in markers):
            found.append(name)
    return found or ["UNKNOWN_OR_CUSTOM"]


def _candidate_urls(text: str, base_url: str, payload: dict[str, Any] | None) -> list[str]:
    raw: list[str] = []
    raw.extend(_URL_RE.findall(text))
    raw.extend(_ATTR_URL_RE.findall(text))
    raw.extend(_CSS_URL_RE.findall(text))
    if payload is not None:
        for value in _walk_strings(payload):
            if value.startswith(("http://", "https://", "/", "./", "../")):
                raw.append(value)

    seen: set[str] = set()
    result: list[str] = []
    for value in raw:
        candidate = urljoin(base_url, value.strip())
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        # Prefer explicit image-like resources and CAPTCHA/puzzle/background names.
        lower_path = (parsed.path or "").lower()
        lower_all = candidate.lower()
        interesting = lower_path.endswith(_IMAGE_EXTENSIONS) or any(
            token in lower_all for token in ("captcha", "puzzle", "slider", "background", "image")
        )
        if not interesting or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
        if len(result) >= 20:
            break
    return result


def _image_meta(data: bytes) -> dict[str, Any] | None:
    try:
        from PIL import Image
        from io import BytesIO

        image = Image.open(BytesIO(data))
        return {
            "format": image.format,
            "width": int(image.width),
            "height": int(image.height),
            "mode": image.mode,
        }
    except Exception:
        return None


def _load_c18_selection() -> tuple[str, str, str | None]:
    data = json.loads(C18_REPORT.read_text(encoding="utf-8"))
    selected = data.get("selected") or {}
    sid = str(selected.get("session_id") or "").strip()
    identity = selected.get("identity") or {}
    expected_ip = str(identity.get("query") or "").strip()
    operator = selected.get("operator")
    if not sid or not expected_ip:
        raise ValueError("C18 selected session/IP missing")
    return sid, expected_ip, str(operator) if operator else None


def main() -> int:
    print("=== Ozon challenge capture/fingerprint C20 ===")
    print("Local clean-room solver preparation. NO browser. NO external solver service.")

    found = _find_c19_challenge()
    if found is None:
        report = {
            "goal": "capture_and_fingerprint_ozon_challenge_for_local_solver",
            "gate": "OZON_CHALLENGE_C19_RAW_EVIDENCE_MISSING",
            "credentials_persisted": False,
            "full_challenge_urls_persisted": False,
        }
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"[EVIDENCE] {report['gate']}")
        return 8

    challenge, raw_path = found
    url_key, challenge_url = _first_challenge_url(challenge)
    if not challenge_url:
        print("[ERROR] C19 challenge JSON has no challenge URL")
        return 8
    if challenge_url.startswith("/"):
        challenge_url = urljoin("https://www.ozon.ru/", challenge_url)

    print(f"C19 challenge source: {raw_path.name}")
    print(f"Challenge URL key: {url_key}")
    print(f"Challenge host: {urlparse(challenge_url).hostname}")
    print("Full challenge URL/token is intentionally NOT printed or persisted.")

    try:
        session_id, expected_ip, operator = _load_c18_selection()
    except Exception as exc:
        print(f"[ERROR] C18_SELECTION_INVALID: {exc}")
        return 8

    proxy_raw = input("Proxy (VISIBLE host:port:user:pass): ").strip()
    try:
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(proxy_raw)
        bound_user, _ = rotate_session(proxy_user, session_id)
        context = ProxyContext.from_city(
            {
                "city": "ozon-c20",
                "proxy": proxy_server,
                "proxy_user": bound_user,
                "proxy_password": proxy_password,
            },
            require_explicit_scheme=True,
        )
    except Exception as exc:
        print(f"[ERROR] PROXY_CONTEXT_INVALID: {type(exc).__name__}: {exc}")
        return 2

    print(f"[1/3] Rechecking exact C18 sticky session ({operator or 'operator unknown'}) ...")
    neutral = curl_request_via_proxy(context, "GET", NEUTRAL_URL, impersonate="chrome", timeout=30)
    neutral_payload = _json_dict(_body_text(neutral.body)) if neutral.ok else None
    observed_ip = str((neutral_payload or {}).get("query") or "")
    same_ip = bool(neutral.ok and observed_ip and observed_ip == expected_ip)
    print(f"      expected={expected_ip} observed={observed_ip or 'NONE'} same_ip={same_ip}")

    if not same_ip:
        report = {
            "goal": "capture_and_fingerprint_ozon_challenge_for_local_solver",
            "challenge_source": raw_path.name,
            "challenge_url": _safe_url_meta(challenge_url),
            "sticky": {"operator": operator, "expected_ip": expected_ip, "observed_ip": observed_ip, "same_ip": False},
            "gate": "OZON_CHALLENGE_STICKY_IP_MISMATCH",
            "credentials_persisted": False,
            "full_challenge_urls_persisted": False,
        }
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"[EVIDENCE] {report['gate']}")
        return 8

    print("[2/3] Fetching challenge through the SAME sticky ProxyContext ...")
    outcome = curl_request_via_proxy(
        context,
        "GET",
        challenge_url,
        impersonate="chrome",
        timeout=45,
        allow_redirects=True,
        headers={"Accept-Language": "ru-RU,ru;q=0.9"},
    )
    body = _body_bytes(outcome.body)
    (OUT_DIR / "challenge_body.bin").write_bytes(body)
    text = _body_text(body)
    fetched_json = _json_dict(text)
    providers = _fingerprint(text, fetched_json)
    urls = _candidate_urls(text, challenge_url, fetched_json)

    print(
        f"      status={outcome.status_code} bytes={len(body)} "
        f"json={fetched_json is not None} fingerprint={','.join(providers)}"
    )

    print(f"[3/3] Capturing up to {len(urls)} candidate image/assets locally ...")
    assets: list[dict[str, Any]] = []
    for index, asset_url in enumerate(urls, 1):
        asset = curl_request_via_proxy(
            context,
            "GET",
            asset_url,
            impersonate="chrome",
            timeout=30,
            allow_redirects=True,
            headers={"Referer": challenge_url},
        )
        data = _body_bytes(asset.body)
        image = _image_meta(data) if asset.ok and data else None
        if asset.ok and data:
            suffix = ".img" if image else ".bin"
            (OUT_DIR / f"asset_{index:02d}{suffix}").write_bytes(data)
        assets.append(
            {
                "index": index,
                "url": _safe_url_meta(asset_url),
                "transport": asset.safe_dict(),
                "bytes": len(data),
                "sha256": _sha256(data) if data else None,
                "image": image,
                "raw_persisted_local_only": bool(asset.ok and data),
            }
        )
        if image:
            print(f"      asset {index}: IMAGE {image['format']} {image['width']}x{image['height']}")

    if not outcome.ok:
        gate = "OZON_CHALLENGE_FETCH_FAILED"
    else:
        gate = "OZON_CHALLENGE_CAPTURED_AND_FINGERPRINTED"

    report = {
        "goal": "capture_and_fingerprint_ozon_challenge_for_local_solver",
        "challenge_source": raw_path.name,
        "challenge_url_key": url_key,
        "challenge_url": _safe_url_meta(challenge_url),
        "challenge_json_keys": sorted(challenge.keys()),
        "sticky": {
            "operator": operator,
            "expected_ip": expected_ip,
            "observed_ip": observed_ip,
            "same_ip": same_ip,
        },
        "fetch": {
            "transport": outcome.safe_dict(),
            "bytes": len(body),
            "sha256": _sha256(body) if body else None,
            "json_decoded": fetched_json is not None,
            "fingerprints": providers,
            "candidate_url_count": len(urls),
        },
        "assets": assets,
        "local_solver_available": True,
        "local_solver_strategies": ["contour_edge_match", "aligned_image_difference"],
        "credentials_persisted": False,
        "cookies_used": False,
        "browser_used": False,
        "external_solver_service_used": False,
        "full_challenge_urls_persisted": False,
        "gate": gate,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[INFO] Safe report: {REPORT_FILE}")
    print(f"[INFO] Raw challenge/assets: {OUT_DIR} (local/Git-ignored)")
    print("[INFO] No credentials, cookies or full signed challenge URLs are persisted.")
    print(f"[EVIDENCE] {gate}")
    return 0 if gate == "OZON_CHALLENGE_CAPTURED_AND_FINGERPRINTED" else 8


if __name__ == "__main__":
    raise SystemExit(main())
