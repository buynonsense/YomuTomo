from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

_ALLOWED_HTTP_SCHEMES = {"http", "https"}


def normalize_http_url(value: object) -> str | None:
    """Return a normalized http(s) URL, or None when the input is unsafe."""
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    parsed = urlsplit(raw)
    if parsed.scheme not in _ALLOWED_HTTP_SCHEMES or not parsed.netloc:
        return None

    path = parsed.path or "/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def is_safe_internal_path(value: object) -> bool:
    if not isinstance(value, str):
        return False

    raw = value.strip()
    if not raw.startswith("/") or raw.startswith("//"):
        return False

    parsed = urlsplit(raw)
    return not parsed.scheme and not parsed.netloc


def safe_href(value: object, default: str = "#") -> str:
    """Normalize a link target for templates and fall back to a harmless placeholder."""
    normalized = normalize_http_url(value)
    if normalized:
        return normalized

    if is_safe_internal_path(value):
        raw = value.strip()
        parsed = urlsplit(raw)
        path = parsed.path or "/"
        return urlunsplit(("", "", path, parsed.query, parsed.fragment))

    return default
