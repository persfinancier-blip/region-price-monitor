from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from browser_proxy_bridge import LocalBrowserProxyBridge
from config import WB_HEADERS
from curl_transport import request_via_proxy as curl_request
from platform_utils import get_chrome_major_version
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
ARCHIVED_WB_NOVOSIBIRSK_COORDS = (55.0084, 82.9357)
ARCHIVED_OZON_CONTROL_SKU = "3129447770"

WB_GEO_URL = "https://user-geo-data.wildberries.ru/get-geo-info"
WB_API_URLS = {
    "v1": "https://card.wb.ru/cards/v1/detail",
    "v2": "https://card.wb.ru/cards/v2/detail",
    "v4": "https://card.wb.ru/cards/v4/detail",
    "u_card_v2": "https://u-card.wb.ru/cards/v2/detail",
}
OZON_COMPOSER_API_URL = "https://www.ozon.ru/api/composer-api.bx/page/json/v2"

_CHALLENGE_TOKENS = (
    "captcha",
    "antibot",
    "checking your browser",
    "проверка браузера",
    "подтвердите, что вы не робот",
    "капча",
)


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
            candidate, _ = decoder.raw_decode(clean[match.start() :])
        except Exception:
            continue
        if isinstance(candidate, dict):
            return candidate
    return None


def _ip_identity(text: str) -> dict[str, Any] | None:
    payload = _json_payload(text)
    if not isinstance(payload, dict):

        def string_field(name: str) -> str | None:
            match = re.search(
                rf'["\']?{re.escape(name)}["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                text,
                re.I,
            )
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


def _same_egress_identity(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if _egress_location(left) is None or _egress_location(right) is None:
        return False
    if _egress_location(left) != _egress_location(right):
        return False
    left_ip = str((left or {}).get("query") or "")
    right_ip = str((right or {}).get("query") or "")
    return bool(left_ip and right_ip and left_ip == right_ip)


def _save_local_body(name: str, text: str) -> str:
    path = LOCAL_PROBES / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _save_neutral_body(name: str, text: str) -> str:
    return _save_local_body(f"neutral_{name}.txt", text)


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


def _extract_wb_dest(payload: dict[str, Any]) -> str | None:
    for key in ("destWithPrefix", "dest"):
        value = payload.get(key)
        if value is None:
            continue
        matches = re.findall(r"-?\d+", str(value))
        if matches:
            return matches[-1]
    xinfo = str(payload.get("xinfo") or "")
    match = re.search(r"(?:^|[?&])dest=([^&]+)", xinfo)
    return match.group(1) if match else None


def _probe_wb_geo(context: ProxyContext, sku: str) -> dict[str, Any]:
    lat, lon = ARCHIVED_WB_NOVOSIBIRSK_COORDS
    outcome = requests_request(
        context,
        "GET",
        WB_GEO_URL,
        params={"currency": "RUB", "latitude": lat, "longitude": lon, "locale": "ru"},
        headers=_wb_probe_headers(sku),
        timeout=30,
    )
    result: dict[str, Any] = {
        "endpoint": WB_GEO_URL,
        "diagnostic_coordinates": [lat, lon],
        "coordinates_source": "archive_novosibirsk_control",
        "transport": outcome.safe_dict(),
    }
    body = _body_text(outcome.body)
    if body:
        result["body_sha256"] = _sha256_text(body)
        result["local_body_file"] = _save_local_body("wb_geo_novosibirsk.txt", body)
    payload = _json_payload(body)
    if isinstance(payload, dict):
        result["observed_dest"] = _extract_wb_dest(payload)
        result["safe_top_level_keys"] = sorted(str(key) for key in payload.keys())[:40]
    else:
        result["observed_dest"] = None
    return result


def _wb_variants(dest: str, observed_dest: str | None = None) -> list[tuple[str, str, str | None]]:
    dest_values: list[tuple[str, str]] = [("input_dest", dest)]
    if observed_dest and observed_dest != dest:
        dest_values.append(("geo_dest", observed_dest))

    variants: list[tuple[str, str, str | None]] = []
    for endpoint_key, endpoint in WB_API_URLS.items():
        for source, value in dest_values:
            variants.append((f"{endpoint_key}_with_{source}", endpoint, value))
        variants.append((f"{endpoint_key}_no_dest", endpoint, None))
    return variants


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
    evidence["stock_path"] = (
        "$.data.products[].sizes[].stocks[].qty"
        if "data" in payload
        else "$.products[].sizes[].stocks[].qty"
    )
    evidence["stock_entries"] = stock_entries
    evidence["stock_qty_samples"] = qty_samples
    evidence["stock_qty_sum_observed"] = qty_sum if numeric_qty_seen else None
    return evidence


def _probe_wb(context: ProxyContext, skus: list[str], dest: str, dest_source: str) -> dict[str, Any]:
    probes: list[dict[str, Any]] = []
    headers = _wb_probe_headers(skus[0])
    geo_probe = _probe_wb_geo(context, skus[0])
    observed_dest = geo_probe.get("observed_dest")

    for label, url, effective_dest in _wb_variants(dest, observed_dest):
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
            item["body_sha256"] = _sha256_text(body)
            item["local_body_file"] = _save_local_body(f"wb_{label}.txt", body)
        payload = _json_payload(body)
        if isinstance(payload, dict):
            item["json_response"] = True
            if outcome.ok:
                item.update(_wb_payload_evidence(payload))
            else:
                item["safe_top_level_keys"] = sorted(str(key) for key in payload.keys())[:40]
        elif body:
            item["json_response"] = False
        probes.append(item)

    cells_with_products = [item["variant"] for item in probes if item.get("product_count", 0) > 0]
    cells_with_stock_path = [item["variant"] for item in probes if item.get("stock_entries", 0) > 0]
    return {
        "comparison_contract": "c03_current_endpoint_and_dest_discovery",
        "diagnostic_dest": dest,
        "diagnostic_dest_source": dest_source,
        "geo_probe": geo_probe,
        "observed_geo_dest": observed_dest,
        "probes": probes,
        "cells_with_products": cells_with_products,
        "cells_with_stock_path": cells_with_stock_path,
        "preliminary_gate": (
            "WB_STOCK_PATH_EVIDENCE_CAPTURED"
            if cells_with_stock_path
            else "WB_ENDPOINT_CONTRACT_UNPROVEN"
            if not cells_with_products
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


def _ozon_city_markers(expected_identity: dict[str, Any] | None) -> list[str]:
    markers: list[str] = []
    if isinstance(expected_identity, dict):
        for value in (expected_identity.get("city"), expected_identity.get("regionName")):
            if value and str(value) not in markers:
                markers.append(str(value))
    if any(value.casefold() == "novosibirsk" for value in markers):
        markers.append("Новосибирск")
    return markers


def _challenge_detected(text: str) -> bool:
    low = text.casefold()
    return any(token.casefold() in low for token in _CHALLENGE_TOKENS)


def _probe_ozon_browser(
    context: ProxyContext,
    sku: str,
    expected_identity: dict[str, Any] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "engine": "headless_chrome_fresh_profile",
        "profile_source": "fresh_temporary",
        "legacy_cookies_supplied": False,
        "human_interaction_allowed": False,
        "browser_projection": context.browser_projection().safe_identity,
    }
    profile_dir = Path(tempfile.mkdtemp(prefix="wave2_ozon_browser_", dir=str(LOCAL_PROBES)))
    driver: Any = None
    try:
        with LocalBrowserProxyBridge(context) as bridge:
            result["proxy_bridge"] = bridge.safe_state
            try:
                import undetected_chromedriver as uc

                options = uc.ChromeOptions()
                options.add_argument("--headless=new")
                options.add_argument(f"--user-data-dir={profile_dir}")
                options.add_argument(f"--proxy-server={bridge.proxy_url}")
                options.add_argument("--disable-quic")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--disable-background-networking")
                options.add_argument("--disable-component-update")
                options.add_argument("--disable-sync")
                options.add_argument("--metrics-recording-only")
                options.add_argument("--no-first-run")
                options.add_argument("--no-default-browser-check")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                version = get_chrome_major_version()
                driver = uc.Chrome(options=options, version_main=version) if version else uc.Chrome(options=options)
                driver.set_page_load_timeout(35)
                driver.set_script_timeout(30)
            except Exception as exc:
                result["startup_error"] = context.redact(f"{type(exc).__name__}: {exc}")
                result["proxy_bridge"] = bridge.safe_state
                result["preliminary_gate"] = "OZON_BROWSER_STARTUP_FAILED"
                return result

            try:
                driver.get(NEUTRAL_PROXY_CHECK_URL)
                neutral_text = driver.find_element("tag name", "body").text
            except Exception as exc:
                result["neutral_navigation_error"] = context.redact(f"{type(exc).__name__}: {exc}")
                result["proxy_bridge"] = bridge.safe_state
                result["preliminary_gate"] = "OZON_BROWSER_PROXY_BINDING_UNPROVEN"
                return result

            browser_identity = _ip_identity(neutral_text)
            result["browser_identity"] = browser_identity
            result["browser_identity_matches_transport"] = _same_egress_identity(
                browser_identity, expected_identity
            )
            result["neutral_body_sha256"] = _sha256_text(neutral_text)
            result["neutral_local_body_file"] = _save_local_body(
                "ozon_browser_neutral.txt", neutral_text
            )
            result["proxy_bridge"] = bridge.safe_state
            if not result["browser_identity_matches_transport"]:
                result["preliminary_gate"] = "OZON_BROWSER_PROXY_BINDING_UNPROVEN"
                return result

            product_url = f"https://www.ozon.ru/product/{sku}/"
            result["product_url"] = product_url
            navigation_error = None
            try:
                driver.get(product_url)
            except Exception as exc:
                navigation_error = context.redact(f"{type(exc).__name__}: {exc}")
            time.sleep(3)

            try:
                page_source = driver.page_source or ""
            except Exception:
                page_source = ""
            try:
                body_text = driver.find_element("tag name", "body").text or ""
            except Exception:
                body_text = ""
            try:
                title = driver.title or ""
            except Exception:
                title = ""
            combined = "\n".join((title, body_text, page_source))
            result["product_navigation_error"] = navigation_error
            result["product_title"] = title[:300]
            result["challenge_detected"] = _challenge_detected(combined)
            result["product_body_sha256"] = _sha256_text(page_source)
            if page_source:
                result["product_local_body_file"] = _save_local_body(
                    f"ozon_browser_product_{sku}.html", page_source
                )
            try:
                result["browser_cookie_names"] = sorted(
                    {str(cookie.get("name")) for cookie in driver.get_cookies() if cookie.get("name")}
                )
            except Exception:
                result["browser_cookie_names"] = []

            markers = _ozon_city_markers(expected_identity)
            marker_hits = [marker for marker in markers if marker.casefold() in combined.casefold()]
            result["city_marker_candidates"] = markers
            result["ozon_content_city_marker_hits"] = marker_hits

            composer_url = f"{OZON_COMPOSER_API_URL}?url=/product/{sku}/"
            result["composer_url"] = composer_url
            fetch_result: Any = None
            try:
                fetch_result = driver.execute_async_script(
                    """
                    const url = arguments[0];
                    const done = arguments[arguments.length - 1];
                    fetch(url, {
                      credentials: 'include',
                      headers: {'accept': 'application/json', 'x-o3-app-name': 'dweb_client'}
                    }).then(async (r) => {
                      done({ok: true, status: r.status,
                            contentType: r.headers.get('content-type'),
                            text: await r.text()});
                    }).catch((e) => done({ok: false, error: String(e)}));
                    """,
                    composer_url,
                )
            except Exception as exc:
                result["composer_fetch_error"] = context.redact(f"{type(exc).__name__}: {exc}")

            composer_text = ""
            composer_status = None
            if isinstance(fetch_result, dict):
                result["composer_fetch_ok"] = bool(fetch_result.get("ok"))
                composer_status = fetch_result.get("status")
                result["composer_status_code"] = composer_status
                result["composer_content_type"] = fetch_result.get("contentType")
                if fetch_result.get("error"):
                    result["composer_fetch_error"] = context.redact(fetch_result.get("error"))
                composer_text = str(fetch_result.get("text") or "")
            else:
                result["composer_fetch_ok"] = False

            if composer_text:
                result["composer_body_sha256"] = _sha256_text(composer_text)
                result["composer_local_body_file"] = _save_local_body(
                    f"ozon_browser_composer_{sku}.txt", composer_text
                )
            payload = _json_payload(composer_text)
            if isinstance(payload, dict):
                result["composer_json_response"] = True
                result.update(_ozon_widget_evidence(payload))
            elif composer_text:
                result["composer_json_response"] = False

            price_evidence = bool(result.get("price_widgets"))
            if result["challenge_detected"]:
                result["preliminary_gate"] = "OZON_BROWSER_HUMAN_ACTION_REQUIRED_CHALLENGE"
            elif composer_status == 200 and price_evidence and marker_hits:
                result["preliminary_gate"] = "OZON_BROWSER_BOOTSTRAP_EVIDENCE_CAPTURED_CITY_MARKER"
            elif composer_status == 200 and price_evidence:
                result["preliminary_gate"] = (
                    "OZON_BROWSER_BOOTSTRAP_HTTP_EVIDENCE_CITY_VERIFICATION_REQUIRED"
                )
            elif composer_status in (403, 429):
                result["preliminary_gate"] = "OZON_BROWSER_SESSION_BLOCKED"
            elif navigation_error:
                result["preliminary_gate"] = "OZON_BROWSER_NAVIGATION_FAILED"
            else:
                result["preliminary_gate"] = "OZON_CONTEXT_CONTRACT_UNPROVEN"
            result["proxy_bridge"] = bridge.safe_state
            return result
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        shutil.rmtree(profile_dir, ignore_errors=True)


def _probe_ozon(
    context: ProxyContext,
    sku: str,
    expected_identity: dict[str, Any] | None,
) -> dict[str, Any]:
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
        result["body_sha256"] = _sha256_text(body)
        result["local_body_file"] = _save_local_body(f"ozon_composer_{sku}.txt", body)

    needs_browser = False
    if outcome.status_code == 403:
        result["http_preliminary_gate"] = (
            "OZON_COMPOSER_NO_COOKIE_BLOCKED_BROWSER_BOOTSTRAP_REQUIRED"
        )
        needs_browser = True
    elif not outcome.ok:
        result["http_preliminary_gate"] = "OZON_CONTEXT_CONTRACT_UNPROVEN"
        return result
    else:
        payload = _json_payload(body)
        if not isinstance(payload, dict):
            result["json_response"] = False
            result["http_preliminary_gate"] = (
                "OZON_COMPOSER_NON_JSON_BROWSER_BOOTSTRAP_REQUIRED"
            )
            needs_browser = True
        else:
            result["json_response"] = True
            result.update(_ozon_widget_evidence(payload))
            if result["price_widgets"]:
                result["preliminary_gate"] = (
                    "OZON_COMPOSER_HTTP_EVIDENCE_CAPTURED_CITY_VERIFICATION_REQUIRED"
                )
            else:
                result["preliminary_gate"] = "OZON_COMPOSER_JSON_NO_PRICE_WIDGET"
            return result

    if needs_browser:
        browser = _probe_ozon_browser(context, sku, expected_identity)
        result["browser_bootstrap"] = browser
        result["preliminary_gate"] = browser.get(
            "preliminary_gate", "OZON_CONTEXT_CONTRACT_UNPROVEN"
        )
    return result


def main() -> int:
    print("=== G01 Wave 2 live evidence probe ===")
    print("Credentials are used only in memory and are not written to the report.")
    print("This run extends WB endpoint/dest evidence and, when needed, performs a zero-human headless Ozon bootstrap probe.")
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
    proxy_gate_ok = (
        proxy_checks.get("preliminary_gate") == "PROXY_EGRESS_CONTEXT_CONFIRMED_ALL_STACKS"
    )

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
            expected_identity = (proxy_checks.get("native_curl") or {}).get("identity")
            report["ozon"] = _probe_ozon(context, ozon_sku, expected_identity)
        else:
            report["ozon"] = {
                "blocked_by_proxy_check": True,
                "browser_projection": context.browser_projection().safe_identity,
                "preliminary_gate": "OZON_CONTEXT_CONTRACT_UNPROVEN",
            }

    report_file = LOCAL_PROBES / "wave2_probe_report.json"
    report_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\n[INFO] Safe report saved to: {report_file}")
    print("[INFO] Neutral/WB/Ozon probe bodies stay under parser/core/local/probes and are Git-ignored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
