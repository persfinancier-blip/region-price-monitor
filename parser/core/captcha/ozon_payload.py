from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


class OzonEmbeddedChallengeError(ValueError):
    pass


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _b64decode(text: str) -> bytes:
    normalized = text.strip().replace("-", "+").replace("_", "/")
    normalized += "=" * ((4 - len(normalized) % 4) % 4)
    try:
        return base64.b64decode(normalized, validate=False)
    except Exception as exc:
        raise OzonEmbeddedChallengeError(f"invalid base64: {type(exc).__name__}") from exc


def raw_query_value(url: str, key: str) -> str:
    """Read one raw query value without form-style '+' -> space conversion."""
    query = urlsplit(url).query
    for item in query.split("&"):
        if not item:
            continue
        raw_key, sep, raw_value = item.partition("=")
        if unquote(raw_key) == key:
            return unquote(raw_value) if sep else ""
    raise OzonEmbeddedChallengeError(f"query parameter {key!r} missing")


def _validated_https_url(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OzonEmbeddedChallengeError(f"{field} is not a non-empty URL")
    raw = value.strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise OzonEmbeddedChallengeError(f"{field} must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise OzonEmbeddedChallengeError(f"{field} must not contain embedded credentials")
    return raw


def _safe_url(url: str) -> dict[str, Any]:
    parsed = urlsplit(url)
    return {
        "scheme": parsed.scheme.lower(),
        "host": parsed.hostname,
        "path_depth": len([part for part in parsed.path.split("/") if part]),
        "path_suffix": Path(parsed.path).suffix.lower() or None,
        "query_present": bool(parsed.query),
        "url_sha256": _sha(url),
        "full_url_persisted": False,
    }


@dataclass(frozen=True, repr=False)
class OzonEmbeddedChallenge:
    version: str
    challenge_id: str
    token: str
    pp: tuple[float, ...]
    cb: tuple[float, ...]
    support_domain: str | None
    origin_referer: str | None
    timestamp: int | float | None
    image_url: str
    puzzle_url: str
    opaque_prefix_length: int
    captcha_value_sha256: str

    def safe_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "challenge_id_sha256": _sha(self.challenge_id),
            "challenge_id_length": len(self.challenge_id),
            "token_sha256": _sha(self.token),
            "token_length": len(self.token),
            "pp": list(self.pp),
            "cb": list(self.cb),
            "support_domain": self.support_domain,
            "origin_referer": self.origin_referer,
            "timestamp": self.timestamp,
            "image": _safe_url(self.image_url),
            "puzzle": _safe_url(self.puzzle_url),
            "opaque_prefix_length": self.opaque_prefix_length,
            "captcha_value_sha256": self.captcha_value_sha256,
            "raw_token_persisted": False,
            "full_urls_persisted": False,
        }


def _numeric_tuple(value: Any, field: str, *, min_items: int = 0) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) < min_items:
        raise OzonEmbeddedChallengeError(f"{field} must be a numeric array with >= {min_items} items")
    out: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise OzonEmbeddedChallengeError(f"{field} contains non-numeric item")
        out.append(float(item))
    return tuple(out)


def decode_captcha_value(value: str, *, max_prefix: int = 12) -> OzonEmbeddedChallenge:
    if not isinstance(value, str) or not value:
        raise OzonEmbeddedChallengeError("captcha value missing")

    outer_text: str | None = None
    prefix_length: int | None = None
    for cut in range(0, min(max_prefix, len(value))):
        try:
            decoded = _b64decode(value[cut:]).decode("utf-8")
        except Exception:
            continue
        parts = decoded.split(",", 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1] and parts[2].startswith("cp:"):
            outer_text = decoded
            prefix_length = cut
            break

    if outer_text is None or prefix_length is None:
        raise OzonEmbeddedChallengeError("no structurally valid prefixed outer payload found")

    version, challenge_id, token = outer_text.split(",", 2)
    token_parts = token.split(":")
    if len(token_parts) < 4 or token_parts[0] != "cp" or not token_parts[-1]:
        raise OzonEmbeddedChallengeError("cp token structure invalid")

    try:
        inner = json.loads(_b64decode(token_parts[-1]).decode("utf-8"))
    except OzonEmbeddedChallengeError:
        raise
    except Exception as exc:
        raise OzonEmbeddedChallengeError(f"inner payload is not JSON: {type(exc).__name__}") from exc
    if not isinstance(inner, dict):
        raise OzonEmbeddedChallengeError("inner payload must be a JSON object")

    pp = _numeric_tuple(inner.get("pp"), "pp", min_items=3)
    cb = _numeric_tuple(inner.get("cb", []), "cb", min_items=0)
    image_url = _validated_https_url(inner.get("is"), "is")
    puzzle_url = _validated_https_url(inner.get("ps"), "ps")

    support_domain = inner.get("support_domain")
    origin_referer = inner.get("origin_referer")
    timestamp = inner.get("ts")
    if support_domain is not None and not isinstance(support_domain, str):
        raise OzonEmbeddedChallengeError("support_domain must be string or null")
    if origin_referer is not None and not isinstance(origin_referer, str):
        raise OzonEmbeddedChallengeError("origin_referer must be string or null")
    if timestamp is not None and (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))):
        raise OzonEmbeddedChallengeError("ts must be numeric or null")

    return OzonEmbeddedChallenge(
        version=version,
        challenge_id=challenge_id,
        token=token,
        pp=pp,
        cb=cb,
        support_domain=support_domain,
        origin_referer=origin_referer,
        timestamp=timestamp,
        image_url=image_url,
        puzzle_url=puzzle_url,
        opaque_prefix_length=prefix_length,
        captcha_value_sha256=_sha(value),
    )


def decode_captcha_url(captcha_url: str) -> OzonEmbeddedChallenge:
    if not isinstance(captcha_url, str) or not captcha_url:
        raise OzonEmbeddedChallengeError("captcha URL missing")
    parsed = urlsplit(captcha_url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise OzonEmbeddedChallengeError("captcha URL must be absolute HTTPS")
    value = raw_query_value(captcha_url, "captcha")
    return decode_captcha_value(value)
