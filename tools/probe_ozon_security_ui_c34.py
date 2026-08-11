from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

LOCAL_PROXY_FILE = CORE / "local" / "ozon_test_proxy.txt"
OZON_URL = "https://www.ozon.ru/?__rr=1&abt_att=1"


def _load_proxy(cli_proxy: str | None) -> tuple[str, str, str, str]:
    raw = (cli_proxy or "").strip()
    if not raw:
        if not LOCAL_PROXY_FILE.exists():
            raise ValueError(f"cached proxy not found: {LOCAL_PROXY_FILE}")
        raw = LOCAL_PROXY_FILE.read_text(encoding="utf-8").strip()
        print(f"[INFO] Using cached proxy: {LOCAL_PROXY_FILE}")
    if "://" in raw:
        scheme, rest = raw.split("://", 1)
        if scheme.lower().strip() != "https":
            raise ValueError("C34 uses only the C33-proven HTTPS proxy scheme")
    else:
        rest = raw
    parts = rest.split(":", 3)
    if len(parts) != 4:
        raise ValueError("proxy must be host:port:user:pass or https://host:port:user:pass")
    host, port, user, password = (part.strip() for part in parts)
    if not all((host, port, user, password)):
        raise ValueError("proxy fields cannot be blank")
    return host, port, user, password


def _safe_http_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        path = parts.path or "/"
        return f"{parts.scheme}://{host}{path}"
    except Exception:
        return "http://<unparsed>"


def _security_details(response: Any) -> dict[str, Any] | None:
    if response is None:
        return None
    getter = getattr(response, "security_details", None)
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description="C34: diagnose visible Not Secure label vs actual Ozon page security state")
    parser.add_argument("--proxy")
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    print("=== Ozon browser security UI diagnostic C34 ===")
    print("C33-proven HTTPS proxy only. No price request. No CAPTCHA interaction/submission.\n")

    try:
        host, port, user, password = _load_proxy(args.proxy)
    except Exception as exc:
        print(f"[ERROR] C34_PROXY_INVALID: {type(exc).__name__}: {exc}")
        return 2

    try:
        from camoufox.sync_api import Camoufox
    except ImportError:
        from camoufox import Camoufox

    if args.visible:
        headless_mode: bool | str = False
    elif platform.system().lower() == "linux":
        headless_mode = "virtual"
    else:
        headless_mode = True

    kwargs: dict[str, Any] = {
        "os": "windows",
        "headless": headless_mode,
        "geoip": True,
        "humanize": 2.0,
        "locale": "ru-RU",
        "proxy": {
            "server": f"https://{host}:{port}",
            "username": user,
            "password": password,
        },
    }

    insecure_requests: list[dict[str, str]] = []
    console_warnings: list[str] = []

    try:
        with Camoufox(**kwargs) as browser:
            page = browser.new_page()

            def on_request(request: Any) -> None:
                url = str(getattr(request, "url", "") or "")
                if url.lower().startswith("http://"):
                    insecure_requests.append({
                        "type": str(getattr(request, "resource_type", "") or "unknown"),
                        "url": _safe_http_url(url),
                    })

            def on_console(message: Any) -> None:
                try:
                    text = str(message.text or "")
                except Exception:
                    text = str(message)
                low = text.lower()
                if "mixed content" in low or "insecure" in low or "blocked" in low:
                    console_warnings.append(text[:500])

            page.on("request", on_request)
            page.on("console", on_console)

            response = page.goto(OZON_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            state = page.evaluate(
                """() => ({
                    href: location.href,
                    protocol: location.protocol,
                    secureContext: window.isSecureContext,
                    httpAttrs: Array.from(document.querySelectorAll('[src^="http://"], [href^="http://"]'))
                      .slice(0, 50)
                      .map(el => el.getAttribute('src') || el.getAttribute('href') || '')
                      .filter(Boolean),
                    perfHttp: performance.getEntriesByType('resource')
                      .map(e => e.name)
                      .filter(name => typeof name === 'string' && name.startsWith('http://'))
                      .slice(0, 50)
                })"""
            )

            details = _security_details(response) or {}
            final_url = str((state or {}).get("href") or page.url or "")
            protocol = str((state or {}).get("protocol") or "")
            secure_context = bool((state or {}).get("secureContext"))
            status = int(response.status) if response is not None else None
            subject = str(details.get("subjectName") or "")
            issuer = str(details.get("issuer") or "")
            tls_protocol = str(details.get("protocol") or "")

            dom_http_raw = list((state or {}).get("httpAttrs") or [])
            perf_http_raw = list((state or {}).get("perfHttp") or [])
            dom_http = [_safe_http_url(str(url)) for url in dom_http_raw]
            perf_http = [_safe_http_url(str(url)) for url in perf_http_raw]

            print(f"main_status={status}")
            print(f"main_final_url={final_url}")
            print(f"main_protocol={protocol}")
            print(f"main_secure_context={secure_context}")
            print(f"main_tls_protocol={tls_protocol or '-'}")
            print(f"main_cert_subject={subject or '-'}")
            print(f"main_cert_issuer={issuer or '-'}")
            print(f"network_http_requests={len(insecure_requests)}")
            print(f"dom_http_attributes={len(dom_http)}")
            print(f"performance_http_resources={len(perf_http)}")
            print(f"console_security_warnings={len(console_warnings)}")

            for item in insecure_requests[:10]:
                print(f"http_request type={item['type']} url={item['url']}")
            for url in dom_http[:10]:
                print(f"dom_http url={url}")
            for url in perf_http[:10]:
                print(f"perf_http url={url}")
            for warning in console_warnings[:10]:
                print(f"console_warning={warning}")

            main_tls_ok = bool(
                final_url.lower().startswith("https://")
                and protocol == "https:"
                and secure_context
                and tls_protocol
                and subject.endswith("ozon.ru")
            )
            mixed_observed = bool(insecure_requests or dom_http or perf_http)

            print("\n=== C34 SUMMARY ===")
            print(f"main_tls_ok={main_tls_ok}")
            print(f"mixed_content_observed={mixed_observed}")

            if not main_tls_ok:
                print("[EVIDENCE] OZON_C34_MAIN_TLS_NOT_PROVEN")
                return 8
            if mixed_observed:
                print("[EVIDENCE] OZON_C34_MIXED_HTTP_CONTENT_OBSERVED")
                return 8
            print("[EVIDENCE] OZON_C34_MAIN_TLS_VALID_NO_HTTP_MIXED_CONTENT")
            return 0
    except Exception as exc:
        print(f"[ERROR] C34_BROWSER_FAILED: {type(exc).__name__}: {exc}")
        return 8


if __name__ == "__main__":
    raise SystemExit(main())
