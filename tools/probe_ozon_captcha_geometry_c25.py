from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "parser" / "core"
TOOLS = ROOT / "tools"
for path in (CORE, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from PIL import Image

from browser_proxy_bridge import LocalBrowserProxyBridge
from captcha.ozon_payload import OzonEmbeddedChallengeError, decode_captcha_url
from captcha.slider import solve_piece_by_contour
from mobile_proxy import _decode_json, _parse_combined_proxy, find_mobile_proxy
from platform_utils import get_chrome_major_version
from probe_browser_visibility import _browser_fetch_text
from probe_ozon_reference_entrypoint import DEFAULT_SKU
from probe_ozon_single_run_c23 import _fetch_bytes, _image_meta, _selected_context
from probe_ozon_solver_robustness_c24 import _neutral_identity, _obtain_challenge

LOCAL = CORE / "local" / "probes"
REPORT_FILE = LOCAL / "ozon_captcha_geometry_c25_report.json"
SCREENSHOT_FILE = LOCAL / "ozon_captcha_geometry_c25.png"
NEUTRAL_URL = "https://api.i.pn/json/"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _alpha_bbox_meta(piece_bytes: bytes) -> dict[str, int]:
    with Image.open(BytesIO(piece_bytes)) as image:
        rgba = image.convert("RGBA")
        bbox = rgba.getchannel("A").getbbox()
        if bbox is None:
            raise ValueError("piece alpha bbox is empty")
        x0, y0, x1, y1 = (int(v) for v in bbox)
        return {
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "width": x1 - x0,
            "height": y1 - y0,
            "natural_width": int(rgba.width),
            "natural_height": int(rgba.height),
        }


def _positive(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if number <= 0:
        raise ValueError(f"{name} must be > 0")
    return number


def _compute_geometry(
    *,
    image_rect: dict[str, Any],
    puzzle_rect: dict[str, Any],
    background_natural: tuple[int, int],
    puzzle_natural: tuple[int, int],
    alpha_bbox: dict[str, int],
    solver_x: int,
    solver_y: int,
) -> dict[str, float]:
    image_left = float(image_rect["left"])
    image_top = float(image_rect["top"])
    image_width = _positive(image_rect["width"], "image_rect.width")
    image_height = _positive(image_rect["height"], "image_rect.height")
    puzzle_left = float(puzzle_rect["left"])
    puzzle_top = float(puzzle_rect["top"])
    puzzle_width = _positive(puzzle_rect["width"], "puzzle_rect.width")
    puzzle_height = _positive(puzzle_rect["height"], "puzzle_rect.height")

    bg_nw = _positive(background_natural[0], "background_natural.width")
    bg_nh = _positive(background_natural[1], "background_natural.height")
    pz_nw = _positive(puzzle_natural[0], "puzzle_natural.width")
    pz_nh = _positive(puzzle_natural[1], "puzzle_natural.height")

    bg_scale_x = image_width / bg_nw
    bg_scale_y = image_height / bg_nh
    puzzle_scale_x = puzzle_width / pz_nw
    puzzle_scale_y = puzzle_height / pz_nh

    target_shape_left = image_left + float(solver_x) * bg_scale_x
    target_shape_top = image_top + float(solver_y) * bg_scale_y

    target_element_left = target_shape_left - float(alpha_bbox["x0"]) * puzzle_scale_x
    target_element_top = target_shape_top - float(alpha_bbox["y0"]) * puzzle_scale_y

    return {
        "background_scale_x": bg_scale_x,
        "background_scale_y": bg_scale_y,
        "puzzle_scale_x": puzzle_scale_x,
        "puzzle_scale_y": puzzle_scale_y,
        "target_shape_left": target_shape_left,
        "target_shape_top": target_shape_top,
        "target_element_left": target_element_left,
        "target_element_top": target_element_top,
        "delta_x": target_element_left - puzzle_left,
        "delta_y": target_element_top - puzzle_top,
    }


def _dom_element(driver: Any, selector: str) -> dict[str, Any] | None:
    script = r"""
const el = document.querySelector(arguments[0]);
if (!el) return null;
const r = el.getBoundingClientRect();
const cs = getComputedStyle(el);
return {
  tag: el.tagName,
  left: r.left,
  top: r.top,
  width: r.width,
  height: r.height,
  right: r.right,
  bottom: r.bottom,
  naturalWidth: Number(el.naturalWidth || 0),
  naturalHeight: Number(el.naturalHeight || 0),
  clientWidth: Number(el.clientWidth || 0),
  clientHeight: Number(el.clientHeight || 0),
  position: cs.position,
  cssLeft: cs.left,
  cssTop: cs.top,
  transform: cs.transform,
  display: cs.display,
  visibility: cs.visibility,
  opacity: cs.opacity
};
"""
    result = driver.execute_script(script, selector)
    return result if isinstance(result, dict) else None


def _browser_identity(driver: Any) -> dict[str, Any] | None:
    driver.get(NEUTRAL_URL)
    fetched = _browser_fetch_text(driver, NEUTRAL_URL)
    if not fetched.get("ok"):
        return None
    return _decode_json(fetched.get("text"))


def _write_report(report: dict[str, Any]) -> None:
    LOCAL.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SAFE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[INFO] Safe report: {REPORT_FILE}")
    print(f"[EVIDENCE] {report['gate']}")


def main() -> int:
    LOCAL.mkdir(parents=True, exist_ok=True)
    print("=== Ozon CAPTCHA DOM geometry calibration C25 ===")
    print("fresh sticky -> live challenge -> local solve -> hidden Chrome DOM geometry")
    print("NO click. NO drag. NO pointer/mouse automation. NO challenge submission.")

    proxy_raw = input("Proxy (VISIBLE host:port:user:pass): ").strip()
    sku = input(f"Ozon SKU [Enter = {DEFAULT_SKU}]: ").strip() or DEFAULT_SKU

    try:
        proxy_server, proxy_user, proxy_password = _parse_combined_proxy(proxy_raw)
    except Exception as exc:
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": "OZON_CAPTCHA_GEOMETRY_PROXY_INVALID",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    print("[1/6] Selecting fresh Russian mobile sticky session ...", flush=True)
    selector = find_mobile_proxy(
        proxy_server=proxy_server,
        proxy_user=proxy_user,
        proxy_password=proxy_password,
        tries=15,
        city_label="ozon-c25",
        verbose=True,
    )
    selected = selector.get("selected")
    if not isinstance(selected, dict):
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "selector_gate": selector.get("gate"),
            "gate": "OZON_CAPTCHA_GEOMETRY_MOBILE_PROXY_NOT_SELECTED",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    try:
        context, session_id, selected_ip = _selected_context(
            proxy_server, proxy_user, proxy_password, selected
        )
    except Exception as exc:
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": "OZON_CAPTCHA_GEOMETRY_PROXY_INVALID",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    pre_ip, pre_transport, pre_error = _neutral_identity(context)
    if pre_error or pre_ip != selected_ip:
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "pre_ip": pre_ip,
            "pre_transport": pre_transport,
            "gate": "OZON_CAPTCHA_GEOMETRY_STICKY_IP_MISMATCH",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8
    print(f"      SAME CURRENT IP CONFIRMED: {pre_ip}")

    print("[2/6] Obtaining live Ozon challenge through SAME ProxyContext ...", flush=True)
    challenge, challenge_url, strategy, attempts, data_access = _obtain_challenge(context, sku)
    if data_access is not None:
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "sku": sku,
            "session_id": session_id,
            "selected_ip": selected_ip,
            "data_access": data_access,
            "gate": "OZON_CAPTCHA_GEOMETRY_NOT_NEEDED_DATA_ACCESS_PROVEN",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 0
    if not isinstance(challenge, dict) or not challenge_url:
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "sku": sku,
            "session_id": session_id,
            "selected_ip": selected_ip,
            "entrypoint_attempts": attempts,
            "gate": "OZON_CAPTCHA_GEOMETRY_CHALLENGE_NOT_OBTAINED",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    print("[3/6] Fetching exact images and solving locally ...", flush=True)
    try:
        embedded = decode_captcha_url(challenge_url)
    except OzonEmbeddedChallengeError as exc:
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": "OZON_CAPTCHA_GEOMETRY_PAYLOAD_INVALID",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    bg_bytes, bg_transport = _fetch_bytes(context, embedded.image_url)
    piece_bytes, piece_transport = _fetch_bytes(context, embedded.puzzle_url)
    if (
        not bg_bytes or not piece_bytes
        or not bg_transport.get("ok")
        or not piece_transport.get("ok")
    ):
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "payload": embedded.safe_dict(),
            "background_transport": bg_transport,
            "puzzle_transport": piece_transport,
            "gate": "OZON_CAPTCHA_GEOMETRY_IMAGE_FETCH_FAILED",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    bg_meta = _image_meta(bg_bytes)
    piece_meta = _image_meta(piece_bytes)
    alpha_bbox = _alpha_bbox_meta(piece_bytes)
    solved = solve_piece_by_contour(piece_bytes, bg_bytes)
    if not solved.ok or solved.x is None or solved.y is None:
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "payload": embedded.safe_dict(),
            "solver": solved.safe_dict(),
            "gate": "OZON_CAPTCHA_GEOMETRY_SOLVER_UNCERTAIN",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8
    print(
        f"      solver x={solved.x} y={solved.y} "
        f"confidence={solved.confidence:.6f} alpha_offset=({alpha_bbox['x0']},{alpha_bbox['y0']})"
    )

    print("[4/6] Starting hidden Chrome on SAME ProxyContext and proving browser egress ...", flush=True)
    profile_dir = Path(tempfile.mkdtemp(prefix="rpm_c25_", dir=str(LOCAL)))
    driver: Any = None
    browser_ip = None
    image_dom = None
    puzzle_dom = None
    browser_error = None
    screenshot_saved = False

    try:
        with LocalBrowserProxyBridge(context) as bridge:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait

            options = uc.ChromeOptions()
            options.add_argument(f"--user-data-dir={profile_dir}")
            options.add_argument(f"--proxy-server={bridge.proxy_url}")
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1280,900")
            options.add_argument("--disable-quic")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-background-networking")
            options.add_argument("--disable-component-update")
            options.add_argument("--disable-sync")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")

            version = get_chrome_major_version()
            driver = uc.Chrome(options=options, version_main=version) if version else uc.Chrome(options=options)
            driver.set_page_load_timeout(45)

            identity = _browser_identity(driver)
            browser_ip = str((identity or {}).get("query") or "").strip() or None
            if browser_ip != selected_ip:
                raise RuntimeError(
                    f"browser egress mismatch: expected {selected_ip}, observed {browser_ip}"
                )

            print(f"      BROWSER SAME IP CONFIRMED: {browser_ip}")
            print("[5/6] Rendering live captchaURL and reading #image/#puzzle geometry only ...", flush=True)
            driver.get(challenge_url)
            wait = WebDriverWait(driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#image")))
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#puzzle")))

            image_dom = _dom_element(driver, "#image")
            puzzle_dom = _dom_element(driver, "#puzzle")
            if not image_dom or not puzzle_dom:
                raise RuntimeError("required CAPTCHA DOM elements missing")

            screenshot_saved = bool(driver.save_screenshot(str(SCREENSHOT_FILE)))
    except Exception as exc:
        browser_error = context.redact(f"{type(exc).__name__}: {exc}")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        shutil.rmtree(profile_dir, ignore_errors=True)

    if browser_error or not image_dom or not puzzle_dom:
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "sku": sku,
            "session_id": session_id,
            "operator": selected.get("operator"),
            "selected_ip": selected_ip,
            "browser_ip": browser_ip,
            "browser_error": browser_error,
            "screenshot_saved": screenshot_saved,
            "solver": solved.safe_dict(),
            "gate": "OZON_CAPTCHA_GEOMETRY_BROWSER_DOM_UNPROVEN",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    try:
        geometry = _compute_geometry(
            image_rect=image_dom,
            puzzle_rect=puzzle_dom,
            background_natural=(int(bg_meta["width"]), int(bg_meta["height"])),
            puzzle_natural=(int(piece_meta["width"]), int(piece_meta["height"])),
            alpha_bbox=alpha_bbox,
            solver_x=int(solved.x),
            solver_y=int(solved.y),
        )
    except Exception as exc:
        _write_report({
            "goal": "calibrate_solver_to_live_captcha_dom_geometry",
            "browser_ip": browser_ip,
            "image_dom": image_dom,
            "puzzle_dom": puzzle_dom,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": "OZON_CAPTCHA_GEOMETRY_INVALID",
            "challenge_submitted": False,
            "credentials_persisted": False,
            "full_urls_persisted": False,
        })
        return 8

    print(
        f"      image scale=({geometry['background_scale_x']:.6f},{geometry['background_scale_y']:.6f}) "
        f"puzzle scale=({geometry['puzzle_scale_x']:.6f},{geometry['puzzle_scale_y']:.6f})"
    )
    print(
        f"      DIAGNOSTIC DOM DELTA: dx={geometry['delta_x']:.3f} dy={geometry['delta_y']:.3f}"
    )

    print("[6/6] Rechecking sticky continuity after geometry calibration ...", flush=True)
    post_ip, post_transport, post_error = _neutral_identity(context)
    continuity_ok = not post_error and post_ip == selected_ip
    gate = (
        "OZON_CAPTCHA_DOM_GEOMETRY_CALIBRATED"
        if continuity_ok and screenshot_saved
        else "OZON_CAPTCHA_GEOMETRY_POSTCHECK_FAILED"
    )

    report = {
        "goal": "calibrate_solver_to_live_captcha_dom_geometry",
        "sku": sku,
        "session_id": session_id,
        "operator": selected.get("operator"),
        "selected_ip": selected_ip,
        "pre_ip": pre_ip,
        "browser_ip": browser_ip,
        "post_ip": post_ip,
        "continuity_ok": continuity_ok,
        "challenge_strategy": strategy,
        "challenge_url_sha256": _sha256_text(challenge_url),
        "payload": embedded.safe_dict(),
        "background": {"image": bg_meta, "transport": bg_transport},
        "puzzle": {"image": piece_meta, "transport": piece_transport, "alpha_bbox": alpha_bbox},
        "solver": solved.safe_dict(),
        "dom": {"image": image_dom, "puzzle": puzzle_dom},
        "geometry": geometry,
        "screenshot_saved": screenshot_saved,
        "post_transport": post_transport,
        "challenge_submitted": False,
        "browser_actions_performed": False,
        "credentials_persisted": False,
        "full_urls_persisted": False,
        "gate": gate,
    }
    _write_report(report)
    return 0 if gate == "OZON_CAPTCHA_DOM_GEOMETRY_CALIBRATED" else 8


if __name__ == "__main__":
    raise SystemExit(main())
