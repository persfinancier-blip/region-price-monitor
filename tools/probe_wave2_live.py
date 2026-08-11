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

from config import WB_HEADERS
from curl_transport import request_via_proxy as curl_request
from requests_transport import request_via_proxy as requests_request
from transport import ProxyContext, ProxyContextError, TransportKind

LOCAL_PROBES = CORE / "local" / "probes"
LOCAL_PROBES.mkdir(parents=True, exist_ok=True)

# Neutral provider-independent egress identity check.
NEUTRAL_PROXY_CHECK_URL = "https://api.i.pn/json/"

# Archived live-evidence controls. These are diagnostic defaults only, not new
# mandatory CityRecord fields or production semantic authority.
ARCHIVED_WB_CONTROL_SKU = "629760017"
ARCHIVED_WB_NOVOSIBIRSK_DEST = "-1075267"
ARCHIVED_OZON_CONTROL_SKU = "3129447770"

WB_API_URLS = {
    "v2": "https://card.wb.ru/cards/v2/detail",
    "v4": "https://card.wb.ru/cards/v4/detail",
}
OZON_COMPOSER_API_URL = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"


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


def _wb_probe_headers(sku: str) -> dict[str, str]:
    """Archived proven WB request headers, applied equally to every comparison cell."""
    ua = WB_HEADERS.get("User-Agent", "")
    return {
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Origin": "https://www.wildberries.ru",
        "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx",
    }


def _wb_variants(dest: str) -> list[tuple[str, str, str | None]]:
    return [
        ("v2_with_dest", WB_API_URLS["v2"], dest),
        ("v2_no_dest", WB_API_URLS["v2"], None),
        ("v4_with_dest", WB_API_URLS["v4"], dest),
        ("v4_no_dest", WB_API_URLS["v4"], None),
    ]


def _wb_payload_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("data", payload)
    products = raw.get("products") if isinstance(raw, dict) else None
    products = products if isinstance(products, list) else []
    evidence: dict[str, Any] = {"product_count": len(products)}
    if not products or not isinstance(products[0], dict):
        evidence["stock_path"] = None
        evidence["stock_entries"] = 0
        return evidence

    product = products[0]
    evidence["first_product_id"] = product.get("id")
    evidence["first_product_keys"] = sorted(str(key) for key in product.keys())
    sizes = product.get("sizes") or []
    if isinstance(sizes, list) and sizes and isinstance(sizes[0], dict):
        evidence["first_size_keys"] = sorted(str(key) for key in sizes[0].keys())

    price_sample = None
    qty_samples: list[dict[str, Any]] = []
    qty_sum = 0
    numeric_qty_seen = False
    stock_entries = 0
    for size in sizes if isinstance(sizes, list) else []:
        if not isinstance(size, dict):
            continue
        if price_sample is None and isinstance(size.get("price"), dict):
            price = size["price"]
            price_sample = {
                key: price.get(key)
                for key in ("basic", "product", "total")
                if key in price
            }
        stocks = size.get("stocks") or []
        for stock in stocks if isinstance(stocks, list) else []:
            if not isinstance(stock, dict) or "qty" not in stock:
                continue
            stock_entries += 1
            qty = stock.get("qty")
            if isinstance(qty, (int, float)) and not isinstance(qty, bool):
                qty_sum += qty
                numeric_qty_seen = True
            if len(qty_samples) < 8:
                qty_samples.append({"wh": stock.get("wh"), "qty": qty})

    evidence["price_kopecks_sample"] = price_sample
    evidence["stock_path"] = "$.data.products[].sizes[].stocks[].qty" if "data" in payload else "$.products[].sizes[].stocks[].qty"
    evidence["stock_entries"] = stock_entries
    evidence["stock_qty_samples"] = qty_samples
    evidence["stock_qty_sum_observed"] = qty_sum if numeric_qty_seen else None
    return evidence


def _probe_wb(context: ProxyContext, skus: list[str], dest: str, dest_source: str) -> dict[str, Any]:
    probes: list[dict[str, Any]] = []
    headers = _wb_probe_headers(skus[0])
    for label, url, effective_dest in _wb_variants(dest):
        params: dict[str, Any] = {
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
            url,
            params=params,
            headers=headers,
            timeout=30,
        )
        item: dict[str, Any] = {
            "variant": label,
            "endpoint": url,
            "dest_sent": effective_dest is not None,
            "dest": effective_dest,
            "transport": outcome.safe_dict(),
        }
        body = _body_text(outcome.body)
        if body:
            path = LOCAL_PROBES / f"wb_{label}.json"
            path.write_text(body, encoding="utf-8")
            item["body_sha256"] = _sha256_text(body)
            item["local_body_file"] = str(path)
        if outcome.ok:
            try:
                payload = json.loads(body)
            except Exception as exc:
                item["json_error"] = type(exc).__name__
            else:
                if isinstance(payload, dict):
                    item.update(_wb_payload_evidence(payload))
        probes.append(item)

    cells_with_products = [item["variant"] for item in probes if item.get("product_count", 0) > 0]
    cells_with_stock_path = [item["variant"] for item in probes if item.get("stock_entries", 0) > 0]
    return {
        "comparison_contract": "archived_v2_v4_x_dest_no_dest",
        "diagnostic_dest": dest,
        "diagnostic_dest_source": dest_source,
        "probes": probes,
        "cells_with_products": cells_with_products,
        "cells_with_stock_path": cells_with_stock_path,
        "preliminary_gate": (
            "WB_STOCK_PATH_EVIDENCE_CAPTURED"
            if cells_with_stock_path
            else "WB_STOCK_CONTRACT_UNPROVEN"
        ),
    }


def _ozon_probe_headers(sku: str) -> dict[str, str]:
    """Archived proven composer request shape; contains no cookies or secrets."""
    return {
        "accept": "application/json",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        ),
        "referer": f"https://www.ozon.ru/product/{sku}/",
        "x-o3-app-name": "dweb_client",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }


def _ozon_widget_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    states = payload.get("widgetStates")
    states = states if isinstance(states, dict) else {}
    price_widgets: list[dict[str, Any]] = []
    for key, value in states.items():
        if "webPrice" not in str(key) and "webSale" not in str(key):
            continue
        parsed = value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                parsed = None
        if not isinstance(parsed, dict):
            continue
        safe_fields = {
            field: parsed.get(field)
            for field in ("price", "originalPrice", "cardPrice", "isAvailable")
            if field in parsed
        }
        price_widgets.append({"key": str(key), "fields": safe_fields})
        if len(price_widgets) >= 5:
            break
    out_of_stock_keys = [str(key) for key in states if "webOutOfStock" in str(key)][:5]
    return {
        "widget_state_count": len(states),
        "price_widgets": price_widgets,
        "out_of_stock_widget_keys": out_of_stock_keys,
    }


def _probe_ozon(context: ProxyContext, sku: str) -> dict[str, Any]:
    from curl_cffi import requests as creq

    headers = _ozon_probe_headers(sku)
    outcome = curl_request(
        context,
        "GET",
        OZON_COMPOSER_API_URL,
        client=creq,
        params={"url": f"/product/{sku}/"},
        headers=headers,
        impersonate="chrome",
        timeout=30,
    )
    result: dict[str, Any] = {
        "request_shape": "archived_composer_api_chrome_no_cookie",
        "endpoint": OZON_COMPOSER_API_URL,
        "product_path": f"/product/{sku}/",
        "impersonate": "chrome",
        "cookies_supplied": False,
        "transport": outcome.safe_dict(),
        "browser_projection": context.browser_projection().safe_identity,
    }

    body = _body_text(outcome.body)
    if body:
        path = LOCAL_PROBES / f"ozon_composer_{sku}.txt"
        path.write_text(body, encoding="utf-8")
        result["body_sha256"] = _sha256_text(body)
        result["local_body_file"] = str(path)

    if outcome.status_code == 403:
        result["preliminary_gate"] = "OZON_COMPOSER_NO_COOKIE_BLOCKED_BROWSER_BOOTSTRAP_REQUIRED"
        return result
    if not outcome.ok:
        result["preliminary_gate"] = "OZON_CONTEXT_CONTRACT_UNPROVEN"
        return result

    payload = _json_payload(body)
    if not isinstance(payload, dict):
        result["json_response"] = False
        result["preliminary_gate"] = "OZON_COMPOSER_NON_JSON_BROWSER_BOOTSTRAP_REQUIRED"
        return result

    result["json_response"] = True
    result.update(_ozon_widget_evidence(payload))
    if result["price_widgets"]:
        result["preliminary_gate"] = "OZON_COMPOSER_HTTP_EVIDENCE_CAPTURED_CITY_VERIFICATION_REQUIRED"
    else:
        result["preliminary_gate"] = "OZON_COMPOSER_JSON_NO_PRICE_WIDGET"
    return result


def main() -> int:
    print("=== G01 Wave 2 live evidence probe ===")
    print("Credentials are used only in memory and are not written to the report.")
    print("This run replays archived proven WB/Ozon request shapes after proxy egress confirmation.")
    city = input("City label: ").strip()
    proxy = input("Proxy address (REQUIRED scheme://host:port): ").strip()
    proxy_user = input("Proxy username: ").strip()
    proxy_password = input("Proxy password: ").strip()

    wb_skus_raw = input(
        f"WB SKU(s) [Enter = archived control {ARCHIVED_WB_CONTROL_SKU}; '-' = skip WB]: "
    ).strip()
    wb_dest_raw = input(
        f"WB dest [Enter = archived Novosibirsk {ARCHIVED_WB_NOVOSIBIRSK_DEST}]: "
    ).strip()
    ozon_sku_raw = input(
        f"Ozon SKU [Enter = archived control {ARCHIVED_OZON_CONTROL_SKU}; '-' = skip Ozon]: "
    ).strip()

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

    wb_enabled = wb_skus_raw != "-"
    if wb_enabled:
        effective_wb_raw = wb_skus_raw or ARCHIVED_WB_CONTROL_SKU
        wb_skus = [part.strip() for part in re.split(r"[,;]", effective_wb_raw) if part.strip()]
        effective_dest = wb_dest_raw or ARCHIVED_WB_NOVOSIBIRSK_DEST
        dest_source = "operator" if wb_dest_raw else "archive_novosibirsk_control"
        if proxy_gate_ok:
            report["wb"] = _probe_wb(context, wb_skus, effective_dest, dest_source)
        else:
            report["wb"] = {
                "blocked_by_proxy_check": True,
                "preliminary_gate": "WB_STOCK_CONTRACT_UNPROVEN",
            }

    ozon_enabled = ozon_sku_raw != "-"
    if ozon_enabled:
        ozon_sku = ozon_sku_raw or ARCHIVED_OZON_CONTROL_SKU
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
