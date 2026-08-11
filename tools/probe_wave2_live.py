from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from config import WB_API_URL, WB_HEADERS
from curl_transport import request_via_proxy as curl_request
from requests_transport import request_via_proxy as requests_request
from transport import ProxyContext, ProxyContextError, TransportKind

LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
# Documented JSON endpoint. With no {query}, i.pn returns the current egress IP.
NEUTRAL_PROXY_CHECK_URL = "https://api.i.pn/json/"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _body_text(body: str | bytes | None) -> str:
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return body or ""


def _json_payload(text: str) -> dict[str, Any] | None:
    """Extract one JSON object from plain JSON, BOM text or a surrounding response wrapper."""
    clean = text.lstrip("\ufeff \t\r\n")
    try:
        payload = json.loads(clean)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        return payload

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", clean):
        try:
            candidate, _ = decoder.raw_decode(clean[match.start():])
        except Exception:
            continue
        if isinstance(candidate, dict):
            return candidate
    return None


def _ip_identity(text: str) -> dict[str, Any] | None:
    payload = _json_payload(text)
    if not isinstance(payload, dict):
        # Bounded fallback for providers that wrap the same fields in non-JSON text.
        def string_field(name: str) -> str | None:
            match = re.search(rf'["\']?{re.escape(name)}["\']?\s*[:=]\s*["\']([^"\']+)["\']', text, re.I)
            return match.group(1).strip() if match else None

        city = string_field("city")
        query = string_field("query")
        if not city and not query:
            return None
        payload = {
            "query": query,
            "countryCode": string_field("countryCode"),
            "regionName": string_field("regionName"),
            "city": city,
        }

    return {
        "query": payload.get("query"),
        "countryCode": payload.get("countryCode"),
        "regionName": payload.get("regionName"),
        "city": payload.get("city"),
        "mobile": payload.get("mobile"),
        "proxy": payload.get("proxy"),
        "hosting": payload.get("hosting"),
    }


def _egress_location(identity: dict[str, Any] | None) -> tuple[str, str, str] | None:
    if not isinstance(identity, dict) or not identity.get("city"):
        return None
    return (
        str(identity.get("countryCode") or "").casefold(),
        str(identity.get("regionName") or "").casefold(),
        str(identity.get("city") or "").casefold(),
    )


def _save_neutral_body(name: str, text: str) -> str:
    path = LOCAL_PROBES / f"neutral_{name}.txt"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _stock_candidates(value: Any, path: str = "$") -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            low = str(key).lower()
            if any(token in low for token in ("stock", "qty", "quantity", "balance", "available")):
                sample = child
                if isinstance(sample, (dict, list)):
                    sample = f"<{type(sample).__name__}:{len(sample)}>"
                result.append({"path": child_path, "sample": sample})
            result.extend(_stock_candidates(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value[:20]):
            result.extend(_stock_candidates(child, f"{path}[{index}]"))
    return result


def _city_snippets(text: str, city: str, limit: int = 5) -> list[str]:
    if not city.strip():
        return []
    low = text.lower()
    needle = city.lower()
    snippets = []
    start = 0
    while len(snippets) < limit:
        pos = low.find(needle, start)
        if pos < 0:
            break
        left = max(0, pos - 80)
        right = min(len(text), pos + len(city) + 80)
        snippets.append(re.sub(r"\s+", " ", text[left:right]))
        start = pos + len(needle)
    return snippets


def _native_curl_proxy_check(context: ProxyContext) -> dict[str, Any]:
    curl_bin = shutil.which("curl.exe") or shutil.which("curl")
    if not curl_bin:
        return {"available": False, "ok": False, "error": "CURL_NOT_FOUND"}

    proxy_url = f"{context.scheme}://{context.host}:{context.port}"
    config_text = (
        f'proxy = "{proxy_url}"\n'
        f'proxy-user = "{context.proxy_user}:{context.proxy_password}"\n'
        "silent\n"
        "show-error\n"
        "location\n"
        "max-time = 20\n"
    )
    try:
        cp = subprocess.run(
            [curl_bin, "--config", "-", NEUTRAL_PROXY_CHECK_URL],
            input=config_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=25,
        )
    except Exception as exc:
        return {
            "available": True,
            "ok": False,
            "returncode": None,
            "error": context.redact(f"{type(exc).__name__}: {exc}"),
        }

    stdout = cp.stdout or ""
    stderr = context.redact(cp.stderr or "")
    result: dict[str, Any] = {
        "available": True,
        "ok": cp.returncode == 0 and bool(stdout.strip()),
        "returncode": cp.returncode,
        "stderr": stderr[:500] if stderr else None,
    }
    if stdout:
        result["body_sha256"] = _sha256_text(stdout)
        result["identity"] = _ip_identity(stdout)
        result["local_body_file"] = _save_neutral_body("native_curl", stdout)
    return result


def _proxy_self_check(context: ProxyContext) -> dict[str, Any]:
    native_curl = _native_curl_proxy_check(context)
    requests_outcome = requests_request(context, "GET", NEUTRAL_PROXY_CHECK_URL, timeout=20)
    curl_outcome = curl_request(
        context,
        "GET",
        NEUTRAL_PROXY_CHECK_URL,
        impersonate="edge",
        timeout=20,
    )

    requests_body = _body_text(requests_outcome.body)
    curl_body = _body_text(curl_outcome.body)
    requests_identity = _ip_identity(requests_body) if requests_outcome.ok else None
    curl_identity = _ip_identity(curl_body) if curl_outcome.ok else None
    native_identity = native_curl.get("identity")

    result: dict[str, Any] = {
        "url": NEUTRAL_PROXY_CHECK_URL,
        "proxy_scheme": context.scheme,
        "native_curl": native_curl,
        "requests": requests_outcome.safe_dict(),
        "curl_cffi": curl_outcome.safe_dict(),
        "requests_identity": requests_identity,
        "curl_cffi_identity": curl_identity,
    }
    if requests_outcome.ok:
        result["requests_body_sha256"] = _sha256_text(requests_body)
        result["requests_local_body_file"] = _save_neutral_body("requests", requests_body)
    if curl_outcome.ok:
        result["curl_body_sha256"] = _sha256_text(curl_body)
        result["curl_local_body_file"] = _save_neutral_body("curl_cffi", curl_body)

    native_ok = bool(native_curl.get("ok"))
    all_transport_ok = native_ok and requests_outcome.ok and curl_outcome.ok
    identities = [native_identity, requests_identity, curl_identity]
    locations = [_egress_location(item) for item in identities]
    identities_complete = all(item is not None for item in locations)
    egress_consistent = identities_complete and len(set(locations)) == 1
    observed_city = None
    if egress_consistent and isinstance(native_identity, dict):
        observed_city = native_identity.get("city")

    result["city_label"] = context.city
    result["observed_egress_city"] = observed_city
    result["city_label_matches_egress"] = bool(
        observed_city and str(observed_city).casefold() == context.city.casefold()
    )
    result["all_transport_ok"] = all_transport_ok
    result["all_egress_locations_agree"] = bool(egress_consistent)

    kinds = {requests_outcome.kind, curl_outcome.kind}
    if all_transport_ok and egress_consistent:
        result["preliminary_gate"] = "PROXY_EGRESS_CONTEXT_CONFIRMED_ALL_STACKS"
    elif all_transport_ok and not identities_complete:
        result["preliminary_gate"] = "PROXY_IDENTITY_UNPROVEN"
    elif all_transport_ok and not egress_consistent:
        result["preliminary_gate"] = "PROXY_EGRESS_CONTEXT_MISMATCH"
    elif native_ok and not requests_outcome.ok:
        result["preliminary_gate"] = "REQUESTS_PROXY_PATH_MISMATCH"
    elif native_ok and requests_outcome.ok and not curl_outcome.ok:
        result["preliminary_gate"] = "CURL_CFFI_PROXY_PATH_MISMATCH"
    elif TransportKind.PROXY_AUTH_ERROR in kinds:
        result["preliminary_gate"] = "PROXY_AUTH_REJECTED_OR_MISMATCH"
    elif native_curl.get("available") and not native_ok:
        result["preliminary_gate"] = "PROVIDER_REFERENCE_CURL_FAILED"
    else:
        result["preliminary_gate"] = "PROXY_CONNECTIVITY_UNPROVEN"
    return result


def _probe_wb(context: ProxyContext, skus: list[str], dest: str | None) -> dict[str, Any]:
    probes = []
    variants = [("no_forced_dest", None)]
    if dest:
        variants.append(("with_dest", dest))

    for label, effective_dest in variants:
        params = {"appType": 1, "curr": "rub", "spp": 30, "nm": ";".join(skus)}
        if effective_dest is not None:
            params["dest"] = effective_dest

        outcome = requests_request(
            context,
            "GET",
            WB_API_URL,
            params=params,
            headers=WB_HEADERS,
            timeout=20,
        )
        item: dict[str, Any] = {"variant": label, "transport": outcome.safe_dict()}
        body = _body_text(outcome.body)
        if outcome.ok:
            path = LOCAL_PROBES / f"wb_{label}.json"
            path.write_text(body, encoding="utf-8")
            item["body_sha256"] = _sha256_text(body)
            item["local_body_file"] = str(path)
            try:
                payload = json.loads(body)
            except Exception as exc:
                item["json_error"] = type(exc).__name__
            else:
                raw = payload.get("data") if isinstance(payload, dict) else None
                products = raw.get("products") if isinstance(raw, dict) else payload.get("products") if isinstance(payload, dict) else None
                products = products if isinstance(products, list) else []
                item["product_count"] = len(products)
                if products:
                    item["first_product_keys"] = sorted(str(k) for k in products[0].keys())
                    sizes = products[0].get("sizes") or []
                    if sizes and isinstance(sizes[0], dict):
                        item["first_size_keys"] = sorted(str(k) for k in sizes[0].keys())
                candidates = _stock_candidates(payload)
                unique = []
                seen = set()
                for candidate in candidates:
                    path_key = re.sub(r"\[\d+\]", "[]", candidate["path"])
                    if path_key in seen:
                        continue
                    seen.add(path_key)
                    unique.append(candidate)
                item["stock_candidates"] = unique[:40]
        probes.append(item)

    proven_candidates = any(item.get("stock_candidates") for item in probes)
    return {
        "probes": probes,
        "preliminary_gate": "EVIDENCE_CAPTURED" if proven_candidates else "WB_STOCK_CONTRACT_UNPROVEN",
    }


def _probe_ozon(context: ProxyContext, sku: str) -> dict[str, Any]:
    from curl_cffi import requests as creq

    session = creq.Session(impersonate="edge")
    home = curl_request(context, "GET", "https://www.ozon.ru/", session=session, timeout=20)
    result: dict[str, Any] = {
        "home_transport": home.safe_dict(),
        "browser_projection": context.browser_projection().safe_identity,
    }
    if not home.ok:
        result["preliminary_gate"] = "OZON_CONTEXT_CONTRACT_UNPROVEN"
        return result

    product = curl_request(
        context,
        "GET",
        f"https://www.ozon.ru/product/{sku}/",
        session=session,
        timeout=30,
    )
    result["product_transport"] = product.safe_dict()
    if not product.ok:
        result["preliminary_gate"] = "OZON_CONTEXT_CONTRACT_UNPROVEN"
        return result

    html = _body_text(product.body)
    html_file = LOCAL_PROBES / f"ozon_{sku}.html"
    html_file.write_text(html, encoding="utf-8")
    result["body_sha256"] = _sha256_text(html)
    result["local_body_file"] = str(html_file)
    low = html.lower()
    result["has_webprice_state"] = "state-webprice-" in low
    result["challenge_detected"] = any(
        token in low for token in ("captcha", "checking your browser", "проверка браузера", "капча")
    )
    result["requested_city_literal_found"] = context.city.lower() in low
    result["city_snippets"] = _city_snippets(html, context.city)
    try:
        result["session_cookie_names"] = sorted(session.cookies.get_dict().keys())
    except Exception:
        result["session_cookie_names"] = []

    if result["challenge_detected"] or not result["has_webprice_state"]:
        result["preliminary_gate"] = "OZON_CONTEXT_CONTRACT_UNPROVEN"
    else:
        result["preliminary_gate"] = "HTTP_EVIDENCE_CAPTURED_CITY_VERIFICATION_REQUIRED"
    return result


def main() -> int:
    print("=== G01 Wave 2 live evidence probe ===")
    print("Credentials are used only in memory and are not written to the report.")
    city = input("City label: ").strip()
    proxy = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = input("Proxy password: ").strip()
    wb_skus_raw = input("WB SKU(s), separated by comma [Enter = skip WB]: ").strip()
    wb_dest = input("WB dest [Enter = also/only no-forced-dest probe]: ").strip() or None
    ozon_sku = input("Ozon SKU [Enter = skip Ozon]: ").strip()

    try:
        context = ProxyContext.from_city(
            {
                "city": city,
                "proxy": proxy,
                "proxy_user": proxy_user,
                "proxy_password": proxy_password,
            },
            require_explicit_scheme=True,
        )
    except ProxyContextError as exc:
        print(f"\n[ERROR] PROXY_SCHEME_OR_ADDRESS_INVALID: {exc}")
        print("Use the protocol configured by the provider, for example https://host:443.")
        return 2

    proxy_checks = _proxy_self_check(context)
    report: dict[str, Any] = {
        "proxy_context": context.safe_identity,
        "proxy_checks": proxy_checks,
        "wb": None,
        "ozon": None,
    }

    proxy_gate_ok = proxy_checks.get("preliminary_gate") == "PROXY_EGRESS_CONTEXT_CONFIRMED_ALL_STACKS"

    if wb_skus_raw:
        if proxy_gate_ok:
            wb_skus = [part.strip() for part in re.split(r"[,;]", wb_skus_raw) if part.strip()]
            report["wb"] = _probe_wb(context, wb_skus, wb_dest)
        else:
            report["wb"] = {
                "blocked_by_proxy_check": True,
                "preliminary_gate": "WB_STOCK_CONTRACT_UNPROVEN",
            }
    if ozon_sku:
        if proxy_gate_ok:
            report["ozon"] = _probe_ozon(context, ozon_sku)
        else:
            report["ozon"] = {
                "blocked_by_proxy_check": True,
                "browser_projection": context.browser_projection().safe_identity,
                "preliminary_gate": "OZON_CONTEXT_CONTRACT_UNPROVEN",
            }

    report_file = LOCAL_PROBES / "wave2_probe_report.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\n[INFO] Safe report saved to: {report_file}")
    print("[INFO] Neutral/WB/Ozon probe bodies stay under parser/core/local/probes and are Git-ignored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
