from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.services import log_with_time
from app.utils.url import normalize_http_url

RSSHUB_FEED_TIMEOUT_SECONDS = 15


def _strip_html(text: object) -> str:
    if not isinstance(text, str):
        return ""

    cleaned = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    cleaned = cleaned.replace("\u3000", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _force_json_format(url: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["format"] = "json"
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


def _normalize_rsshub_base_url(base_url: str | None = None) -> str | None:
    normalized = normalize_http_url(base_url or settings.RSSHUB_BASE_URL)
    if not normalized:
        return None

    return normalized.rstrip("/")


def _normalize_rsshub_route(value: str, base_url: str | None = None) -> str | None:
    route = value.removeprefix("rsshub://").lstrip("/")
    if not route:
        return None

    base = _normalize_rsshub_base_url(base_url)
    if not base:
        return None

    return _force_json_format(f"{base}/{route}")


def _normalize_rsshub_url(value: str, base_url: str | None = None) -> str | None:
    normalized = normalize_http_url(value)
    if not normalized:
        return None

    parsed = urlsplit(normalized)
    base = _normalize_rsshub_base_url(base_url)
    if not base:
        return None

    base_parsed = urlsplit(base)
    if parsed.netloc != base_parsed.netloc or parsed.scheme != base_parsed.scheme:
        return None

    base_path = base_parsed.path or "/"
    if base_path != "/":
        prefix = base_path.rstrip("/")
        if parsed.path != prefix and not parsed.path.startswith(f"{prefix}/"):
            return None

    return _force_json_format(normalized)


def normalize_rsshub_source_url(source_url: str | None, base_url: str | None = None) -> str | None:
    """Normalize an RSSHub route or URL to a JSON feed endpoint."""
    if not isinstance(source_url, str):
        return None

    value = source_url.strip()
    if not value:
        return None

    if value.startswith("rsshub://"):
        return _normalize_rsshub_route(value, base_url)

    if value.startswith("http://") or value.startswith("https://"):
        return _normalize_rsshub_url(value, base_url)

    if "/" in value and " " not in value:
        return _normalize_rsshub_route(f"rsshub://{value.lstrip('/')}", base_url)

    return None


def _extract_items_from_payload(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("items", "item"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

    data = payload.get("data")
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

    return []


def _normalize_feed_item(raw_item: dict, source_feed_url: str) -> dict | None:
    title = _strip_html(raw_item.get("title") or raw_item.get("name"))
    if not title:
        return None

    link = raw_item.get("url") or raw_item.get("link") or raw_item.get("external_url") or raw_item.get("id")
    if not isinstance(link, str):
        return None

    link = link.strip()
    if not link:
        return None

    summary_text = _strip_html(raw_item.get("summary") or raw_item.get("description"))
    content_text = _strip_html(raw_item.get("content_text") or raw_item.get("content_html"))
    content = content_text or summary_text or title
    outline = summary_text or content[:200]

    published_at = raw_item.get("date_published") or raw_item.get("published_at") or raw_item.get("updated")
    if not isinstance(published_at, str):
        published_at = None

    news_id = raw_item.get("id")
    if not isinstance(news_id, str) or not news_id.strip():
        news_id = link

    normalized = {
        "title": title,
        "title_with_ruby": None,
        "url": link,
        "source_url": link,
        "source_feed_url": source_feed_url,
        "news_id": news_id,
        "outline": outline,
        "content": content,
    }
    if published_at:
        normalized["published_at"] = published_at

    return normalized


def fetch_rsshub_feed_items(source_url: str | None, limit: int = 12) -> list[dict]:
    """Fetch and normalize items from an RSSHub route."""
    normalized_source = normalize_rsshub_source_url(source_url)
    if not normalized_source:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    response = requests.get(normalized_source, headers=headers, timeout=RSSHUB_FEED_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()

    items = _extract_items_from_payload(payload)
    normalized_items: list[dict] = []
    max_items = max(limit, 0)

    for raw_item in items:
        normalized_item = _normalize_feed_item(raw_item, normalized_source)
        if not normalized_item:
            continue
        normalized_items.append(normalized_item)
        if max_items and len(normalized_items) >= max_items:
            break

    return normalized_items


def first_item_content(source_url: str | None) -> str | None:
    """Fetch the first item body from an RSSHub source."""
    try:
        items = fetch_rsshub_feed_items(source_url, limit=1)
    except Exception as e:
        log_with_time(f"获取 RSSHub 订阅源内容失败 source_url={source_url}: {e}")
        return None

    if not items:
        return None

    item = items[0]
    for key in ("content", "outline", "title"):
        value = item.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text

    return None
