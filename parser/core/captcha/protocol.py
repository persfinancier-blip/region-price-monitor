from __future__ import annotations

from dataclasses import asdict, dataclass
import base64
import re
from typing import Iterable
from urllib.parse import urljoin, urlparse


@dataclass(frozen=True)
class ProtocolCandidate:
    kind: str
    value: str
    method: str | None = None
    risky_submission_like: bool = False

    def safe_dict(self) -> dict[str, object]:
        parsed = urlparse(self.value)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            safe_value = f"{parsed.scheme}://{parsed.hostname}{parsed.path or '/'}"
        else:
            safe_value = self.value.split("?", 1)[0]
        return {
            "kind": self.kind,
            "value": safe_value,
            "method": self.method,
            "risky_submission_like": self.risky_submission_like,
        }


_ABSOLUTE_URL_RE = re.compile(r"https?://[^\s\"'<>\\)]+", re.IGNORECASE)
_QUOTED_RE = re.compile(r"(?P<q>[\"'])(?P<s>(?:\\.|(?!\1).){1,500}?)(?P=q)", re.DOTALL)
_FETCH_RE = re.compile(r"fetch\s*\(\s*([\"'])(?P<url>[^\"']+)\1", re.IGNORECASE)
_XHR_OPEN_RE = re.compile(
    r"\.open\s*\(\s*([\"'])(?P<method>GET|POST|PUT|PATCH|DELETE)\1\s*,\s*([\"'])(?P<url>[^\"']+)\3",
    re.IGNORECASE,
)
_SOURCE_MAP_RE = re.compile(r"sourceMappingURL\s*=\s*(?P<url>[^\s*]+)", re.IGNORECASE)
_DATA_IMAGE_RE = re.compile(
    r"data:image/(?P<fmt>png|jpeg|jpg|webp|gif|bmp);base64,(?P<data>[A-Za-z0-9+/=]+)",
    re.IGNORECASE,
)
_PATH_HINTS = (
    "captcha", "challenge", "slider", "puzzle", "image", "background", "piece",
    "verify", "validate", "submit", "solve", "check", "init", "incident", "api",
)
_RISKY_HINTS = ("verify", "validate", "submit", "solve", "check", "confirm")
_IMAGE_HINTS = ("image", "background", "piece", "puzzle", "slider", ".png", ".jpg", ".jpeg", ".webp")


def _unescape_js_string(value: str) -> str:
    # Conservative unescape sufficient for URL/path discovery. Never execute JS.
    return (
        value.replace(r"\/", "/")
        .replace(r"\u002F", "/")
        .replace(r"\u003A", ":")
        .replace(r"\u0026", "&")
    )


def _looks_interesting(value: str) -> bool:
    low = value.lower()
    return any(token in low for token in _PATH_HINTS)


def _looks_urlish(value: str) -> bool:
    value = value.strip()
    if value.startswith(("http://", "https://", "/", "./", "../")):
        return True
    low = value.lower()
    return ("/" in value and _looks_interesting(value)) or low.startswith("api/")


def _risky(value: str) -> bool:
    low = value.lower()
    return any(token in low for token in _RISKY_HINTS)


def _dedupe(items: Iterable[ProtocolCandidate]) -> list[ProtocolCandidate]:
    out: list[ProtocolCandidate] = []
    seen: set[tuple[str, str, str | None]] = set()
    for item in items:
        key = (item.kind, item.value, item.method)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def analyze_protocol_surface(text: str, *, base_url: str | None = None) -> dict[str, object]:
    candidates: list[ProtocolCandidate] = []

    for match in _FETCH_RE.finditer(text):
        value = _unescape_js_string(match.group("url"))
        resolved = urljoin(base_url, value) if base_url else value
        candidates.append(ProtocolCandidate("fetch", resolved, "GET", _risky(value)))

    for match in _XHR_OPEN_RE.finditer(text):
        value = _unescape_js_string(match.group("url"))
        method = match.group("method").upper()
        resolved = urljoin(base_url, value) if base_url else value
        candidates.append(ProtocolCandidate("xhr", resolved, method, method != "GET" or _risky(value)))

    for match in _ABSOLUTE_URL_RE.finditer(text):
        value = _unescape_js_string(match.group(0))
        if _looks_interesting(value):
            candidates.append(ProtocolCandidate("absolute_url", value, None, _risky(value)))

    for match in _QUOTED_RE.finditer(text):
        value = _unescape_js_string(match.group("s")).strip()
        if not _looks_urlish(value) or not _looks_interesting(value):
            continue
        resolved = urljoin(base_url, value) if base_url and value.startswith(("/", "./", "../")) else value
        candidates.append(ProtocolCandidate("string_path", resolved, None, _risky(value)))

    source_maps: list[str] = []
    for match in _SOURCE_MAP_RE.finditer(text):
        value = match.group("url").strip().strip("'\"")
        if value.startswith("data:"):
            continue
        source_maps.append(urljoin(base_url, value) if base_url else value)

    data_images: list[dict[str, object]] = []
    for index, match in enumerate(_DATA_IMAGE_RE.finditer(text), 1):
        try:
            raw = base64.b64decode(match.group("data"), validate=False)
        except Exception:
            continue
        data_images.append({
            "index": index,
            "format": match.group("fmt").lower(),
            "bytes": len(raw),
            "data": raw,
        })

    unique = _dedupe(candidates)
    safe_get_candidates = [
        item for item in unique
        if item.method in {None, "GET"}
        and not item.risky_submission_like
        and any(token in item.value.lower() for token in _IMAGE_HINTS + ("captcha", "challenge", "init", "api"))
    ]

    return {
        "candidates": unique,
        "safe_get_candidates": safe_get_candidates,
        "source_maps": list(dict.fromkeys(source_maps)),
        "data_images": data_images,
    }
