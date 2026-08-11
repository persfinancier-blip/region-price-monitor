from __future__ import annotations

from getpass import getpass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from config import WB_API_URL, WB_HEADERS
from curl_transport import request_via_proxy as curl_request
from requests_transport import request_via_proxy as requests_request
from transport import ProxyContext, TransportKind

LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)
NEUTRAL_PROXY_CHECK_URL = "https://api.ipify.org?format=json"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _body_text(body: str | bytes | None) -> str:
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return body or ""


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
        snippet = re.sub(r"\s+", " ", text[left:right])
        snippets.append(snippet)
        start = pos + len(needle)
    return snippets


def _proxy_self_check(context: ProxyContext) -> dict[str, Any]:
    requests_outcome = requests_request(
        context,
        "GET",
        NEUTRAL_PROXY_CHECK_URL,
        timeout=20,
    )
    curl_outcome = curl_request(
        context,
        "GET",
        NEUTRAL_PROXY_CHECK_URL,
        impersonate="edge",
        timeout=20,
    )
    result: dict[str, Any] = {
        "url": NEUTRAL_PROXY_CHECK_URL,
        "requests": requests_outcome.safe_dict(),
        "curl_cffi": curl_outcome.safe_dict(),
    }
    if requests_outcome.ok:
        result["requests_body_sha256"] = _sha256_text(_body_text(requests_outcome.body))
    if curl_outcome.ok:
        result["curl_body_sha256"] = _sha256_text(_body_text(curl_outcome.body))

    kinds = {requests_outcome.kind, curl_outcome.kind}
    if requests_outcome.ok and curl_outcome.ok:
        result["preliminary_gate"] = "PROXY_CONNECTIVITY_CONFIRMED"
    elif TransportKind.PROXY_AUTH_ERROR in kinds:
        result["preliminary_gate"] = "PROXY_AUTH_REJECTED_OR_MISMATCH"
    else:
        result["preliminary_gate"] = "PROXY_CONNECTIVITY_UNPROVEN"
    return result


def _probe_wb(context: ProxyContext, skus: list[str], dest: str | None) -> dict[str, Any]:
    probes = []
    variants = [("no_forced_dest", None)]
    if dest:
        variants.append(("with_dest", dest))

    for label, effective_dest in variants:
        params = {
            "appType": 1,
            "curr": "rub",
            "spp": 30,
            "nm": ";".join(skus),
        }
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
        item: dict[str, Any] = {
            "variant": label,
            "transport": outcome.safe_dict(),
        }
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
    home = curl_request(
        context,
        "GET",
        "https://www.ozon.ru/",
        session=session,
        timeout=20,
    )
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
    result["challenge_detected"] = any(token in low for token in ("captcha", "checking your browser", "проверка браузера", "капча"))
    result["requested_city_literal_found"] = context.city.lower() in low
    result["city_snippets"] = _city_snippets(html, context.city)
    try:
        result["session_cookie_names"] = sorted(session.cookies.get_dict().keys())
    except Exception:
        result["session_cookie_names"] = []

    if result["challenge_detected"]:
        result["preliminary_gate"] = "OZON_CONTEXT_CONTRACT_UNPROVEN"
    elif not result["has_webprice_state"]:
        result["preliminary_gate"] = "OZON_CONTEXT_CONTRACT_UNPROVEN"
    else:
        result["preliminary_gate"] = "HTTP_EVIDENCE_CAPTURED_CITY_VERIFICATION_REQUIRED"
    return result


def main() -> int:
    print("=== G01 Wave 2 live evidence probe ===")
    print("Credentials are used only in memory and are not written to the report.")
    city = input("City name: ").strip()
    proxy = input("Proxy address (host:port or scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = getpass("Proxy password (hidden): ")
    wb_skus_raw = input("WB SKU(s), separated by comma [Enter = skip WB]: ").strip()
    wb_dest = input("WB dest [Enter = also/only no-forced-dest probe]: ").strip() or None
    ozon_sku = input("Ozon SKU [Enter = skip Ozon]: ").strip()

    context = ProxyContext.from_city({
        "city": city,
        "proxy": proxy,
        "proxy_user": proxy_user,
        "proxy_password": proxy_password,
    })
    report: dict[str, Any] = {
        "proxy_context": context.safe_identity,
        "proxy_checks": _proxy_self_check(context),
        "wb": None,
        "ozon": None,
    }

    requests_proxy_ok = report["proxy_checks"]["requests"]["ok"]
    curl_proxy_ok = report["proxy_checks"]["curl_cffi"]["ok"]

    if wb_skus_raw:
        if requests_proxy_ok:
            wb_skus = [part.strip() for part in re.split(r"[,;]", wb_skus_raw) if part.strip()]
            report["wb"] = _probe_wb(context, wb_skus, wb_dest)
        else:
            report["wb"] = {
                "blocked_by_proxy_check": True,
                "preliminary_gate": "WB_STOCK_CONTRACT_UNPROVEN",
            }
    if ozon_sku:
        if curl_proxy_ok:
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
    print("[INFO] Raw WB/Ozon bodies, when captured, stay under parser/core/local/probes and are Git-ignored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
