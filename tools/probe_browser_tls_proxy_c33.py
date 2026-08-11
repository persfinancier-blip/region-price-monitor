from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

LOCAL_PROXY_FILE = CORE / "local" / "ozon_test_proxy.txt"
NEUTRAL_HTTPS = "https://example.com/"
OZON_HTTPS = "https://www.ozon.ru/?__rr=1&abt_att=1"


def _load_proxy(cli_proxy: str | None) -> str:
    if cli_proxy and cli_proxy.strip():
        return cli_proxy.strip()
    if LOCAL_PROXY_FILE.exists():
        value = LOCAL_PROXY_FILE.read_text(encoding="utf-8").strip()
        if value:
            print(f"[INFO] Using cached proxy: {LOCAL_PROXY_FILE}")
            return value
    raise ValueError(f"cached proxy not found: {LOCAL_PROXY_FILE}")


def _split_proxy(raw: str) -> tuple[str | None, str, str, str, str]:
    value = raw.strip()
    if not value:
        raise ValueError("proxy is empty")
    supplied_scheme: str | None = None
    rest = value
    if "://" in value:
        supplied_scheme, rest = value.split("://", 1)
        supplied_scheme = supplied_scheme.lower().strip()
    parts = rest.split(":", 3)
    if len(parts) != 4:
        raise ValueError("proxy must be host:port:user:pass or scheme://host:port:user:pass")
    host, port, user, password = (part.strip() for part in parts)
    if not host or not port or not user or not password:
        raise ValueError("proxy fields cannot be blank")
    return supplied_scheme, host, port, user, password


def _security_details(response: Any) -> dict[str, Any] | None:
    if response is None:
        return None
    getter = getattr(response, "security_details", None)
    if not callable(getter):
        return None
    try:
        details = getter()
    except Exception:
        return None
    return details if isinstance(details, dict) else None


def _probe_page(page: Any, url: str) -> dict[str, Any]:
    response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    state = page.evaluate(
        """() => ({
            href: location.href,
            protocol: location.protocol,
            origin: location.origin,
            secureContext: window.isSecureContext
        })"""
    )
    details = _security_details(response)
    final_url = str((state or {}).get("href") or page.url or "")
    protocol = str((state or {}).get("protocol") or "")
    secure_context = bool((state or {}).get("secureContext"))
    status = int(response.status) if response is not None else None
    ok = bool(
        final_url.lower().startswith("https://")
        and protocol == "https:"
        and secure_context
        and status is not None
        and 200 <= status < 500
    )
    return {
        "requested_url": url,
        "final_url": final_url,
        "protocol": protocol,
        "secure_context": secure_context,
        "status": status,
        "security_details": details,
        "secure": ok,
    }


def _print_result(label: str, result: dict[str, Any]) -> None:
    details = result.get("security_details") or {}
    print(
        f"      {label}: status={result.get('status')} protocol={result.get('protocol')} "
        f"secure_context={result.get('secure_context')} secure={result.get('secure')}"
    )
    print(f"      {label}: final_url={result.get('final_url')}")
    if details:
        print(
            f"      {label}: tls_protocol={details.get('protocol')} "
            f"issuer={details.get('issuer')} subject={details.get('subjectName')}"
        )
    else:
        print(f"      {label}: security_details=unavailable")


def _probe_scheme(
    Camoufox: Any,
    *,
    scheme: str,
    host: str,
    port: str,
    user: str,
    password: str,
    visible: bool,
) -> dict[str, Any]:
    if visible:
        headless_mode: bool | str = False
    elif platform.system().lower() == "linux":
        headless_mode = "virtual"
    else:
        headless_mode = True

    proxy_server = f"{scheme}://{host}:{port}"
    kwargs: dict[str, Any] = {
        "os": "windows",
        "headless": headless_mode,
        "geoip": True,
        "humanize": 2.0,
        "locale": "ru-RU",
        "proxy": {
            "server": proxy_server,
            "username": user,
            "password": password,
        },
    }

    print(f"\n[{scheme.upper()} proxy candidate] {scheme}://{host}:{port}")
    try:
        with Camoufox(**kwargs) as browser:
            neutral_page = browser.new_page()
            neutral = _probe_page(neutral_page, NEUTRAL_HTTPS)
            _print_result("neutral", neutral)

            ozon_page = browser.new_page()
            ozon = _probe_page(ozon_page, OZON_HTTPS)
            _print_result("ozon", ozon)

            return {
                "scheme": scheme,
                "neutral": neutral,
                "ozon": ozon,
                "secure": bool(neutral.get("secure") and ozon.get("secure")),
            }
    except Exception as exc:
        print(f"      browser_error={type(exc).__name__}: {exc}")
        return {"scheme": scheme, "secure": False, "error": type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="C33: verify browser HTTPS security through the cached proxy before any Ozon anti-bot work"
    )
    parser.add_argument("--proxy")
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    print("=== Browser TLS / proxy security preflight C33 ===")
    print("No CAPTCHA interaction. No price request. Compare proxy protocol candidates only.\n")

    try:
        raw = _load_proxy(args.proxy)
        supplied_scheme, host, port, user, password = _split_proxy(raw)
    except Exception as exc:
        print(f"[ERROR] C33_PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    print(f"proxy_endpoint={host}:{port}")
    print(f"scheme_in_cached_value={supplied_scheme or 'NONE'}")

    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        from camoufox import Camoufox

    schemes = [supplied_scheme] if supplied_scheme in {"http", "https"} else ["http", "https"]
    results = [
        _probe_scheme(
            Camoufox,
            scheme=scheme,
            host=host,
            port=port,
            user=user,
            password=password,
            visible=args.visible,
        )
        for scheme in schemes
    ]

    secure = [item for item in results if item.get("secure")]
    print("\n=== C33 SUMMARY ===")
    for item in results:
        print(f"scheme={item.get('scheme')} secure={item.get('secure')} error={item.get('error') or '-'}")

    if len(secure) == 1:
        chosen = str(secure[0]["scheme"])
        print(f"[EVIDENCE] OZON_C33_SECURE_PROXY_SCHEME_PROVEN scheme={chosen}")
        return 0
    if len(secure) > 1:
        print("[EVIDENCE] OZON_C33_BOTH_PROXY_SCHEMES_SECURE")
        return 0

    print("[EVIDENCE] OZON_C33_NO_SECURE_BROWSER_PROXY_PATH")
    return 8


if __name__ == "__main__":
    raise SystemExit(main())
