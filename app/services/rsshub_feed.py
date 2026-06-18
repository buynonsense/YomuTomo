from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.services import log_with_time
from app.utils.url import normalize_http_url

RSSHUB_FEED_TIMEOUT_SECONDS = 30
# 瞬时网络错误重试次数。RSSHub 公共实例经常中途断流（IncompleteRead / Connection
# broken），一次失败不代表路由真的不可用，重试 1-2 次通常就能拿到完整 body
RSSHUB_FEED_RETRY_ATTEMPTS = 3
RSSHUB_FEED_RETRY_BACKOFF_SECONDS = 1.5


# 哪些 requests 异常属于"瞬时"，可安全重试
_RETRYABLE_REQUEST_EXC = (
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


class RSSHubFetchError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        source_url: str | None = None,
        normalized_source_url: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.source_url = source_url
        self.normalized_source_url = normalized_source_url
        self.status_code = status_code


def _strip_html(text: object) -> str:
    if not isinstance(text, str):
        return ""

    cleaned = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    cleaned = cleaned.replace("\u3000", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _force_json_format(url: str) -> str:
    return _set_rsshub_format(url, "json")


def _set_rsshub_format(url: str, feed_format: str | None) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if feed_format is None:
        query.pop("format", None)
    else:
        query["format"] = feed_format
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


def _normalize_rsshub_route(
    value: str, base_url: str | None = None, feed_format: str | None = "json"
) -> str | None:
    route = value.removeprefix("rsshub://").lstrip("/")
    if not route:
        return None

    base = _normalize_rsshub_base_url(base_url)
    if not base:
        return None

    return _set_rsshub_format(f"{base}/{route}", feed_format)


def _normalize_rsshub_url(
    value: str, base_url: str | None = None, feed_format: str | None = "json"
) -> str | None:
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

    return _set_rsshub_format(normalized, feed_format)


def _describe_rsshub_request_error(
    exc: Exception, normalized_source: str, attempts: int = 1
) -> str:
    if isinstance(exc, requests.Timeout):
        return f"RSSHub 请求超时，请稍后重试：{normalized_source}"
    if isinstance(exc, requests.exceptions.ChunkedEncodingError):
        # 上游连接中途断开（Cloudflare / 公共实例流量节流常见）
        return (
            f"RSSHub 上游连接中途断开（{exc}），已重试 {attempts} 次仍失败：{normalized_source}。"
            "建议稍后重试，或更换 RSSHUB_BASE_URL / 自部署 RSSHub。"
        )

    return f"RSSHub 请求失败：{normalized_source}（{exc}）"


def _describe_rsshub_status_error(
    status_code: int,
    normalized_source: str,
    body_snippet: str | None = None,
) -> str:
    if status_code == 403:
        preview = (body_snippet or "").strip().replace("\n", " ")[:500]
        body_hint = (
            f"上游响应摘要：{preview}"
            if preview
            else "上游未返回可读响应体（可能是 Cloudflare 拦截页）"
        )
        return (
            "RSSHub 公共实例已对本机 IP 返回 403。"
            f"请更换 RSSHUB_BASE_URL（如 {settings.RSSHUB_BASE_URL}）或自部署 RSSHub。"
            f"当前请求：{normalized_source}。"
            f"{body_hint}"
        )
    if status_code == 404:
        return f"RSSHub 路由不存在或尚未支持：{normalized_source}"
    if status_code == 429:
        return f"RSSHub 上游请求过于频繁，请稍后重试：{normalized_source}"
    if 500 <= status_code < 600:
        return f"RSSHub 上游服务暂时不可用（HTTP {status_code}）：{normalized_source}"

    return f"RSSHub 请求失败（HTTP {status_code}）：{normalized_source}"


def normalize_rsshub_source_url(
    source_url: str | None,
    base_url: str | None = None,
    feed_format: str | None = "json",
) -> str | None:
    """Normalize an RSSHub route or URL to a JSON feed endpoint."""
    if not isinstance(source_url, str):
        return None

    value = source_url.strip()
    if not value:
        return None

    if value.startswith("rsshub://"):
        return _normalize_rsshub_route(value, base_url, feed_format=feed_format)

    if value.startswith("http://") or value.startswith("https://"):
        return _normalize_rsshub_url(value, base_url, feed_format=feed_format)

    if "/" in value and " " not in value:
        return _normalize_rsshub_route(
            f"rsshub://{value.lstrip('/')}", base_url, feed_format=feed_format
        )

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


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""

    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, *names: str) -> str | None:
    wanted = {name.lower() for name in names}
    for child in list(element):
        if _local_name(child.tag) not in wanted:
            continue

        text = "".join(child.itertext()).strip()
        if text:
            return text

    return None


def _child_href(element: ET.Element, *names: str) -> str | None:
    wanted = {name.lower() for name in names}
    for child in list(element):
        if _local_name(child.tag) not in wanted:
            continue

        href = child.attrib.get("href")
        if isinstance(href, str):
            text = href.strip()
            if text:
                return text

        text = "".join(child.itertext()).strip()
        if text:
            return text

    return None


def _extract_items_from_xml_payload(payload: str) -> list[dict]:
    if not isinstance(payload, str):
        return []

    text = payload.strip()
    if not text:
        return []

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise RSSHubFetchError(f"RSSHub 返回了无法解析的 XML 内容：{exc}") from exc

    items: list[dict] = []
    for element in root.iter():
        local_tag = _local_name(element.tag)
        if local_tag not in {"item", "entry"}:
            continue

        title = _child_text(element, "title")
        link = _child_href(element, "link")
        summary = _child_text(element, "summary", "description")
        content_text = _child_text(element, "content", "encoded")
        published_at = _child_text(element, "pubdate", "published", "updated")
        news_id = _child_text(element, "id", "guid")

        raw_item: dict[str, str] = {}
        if title:
            raw_item["title"] = title
        if link:
            raw_item["url"] = link
            raw_item["link"] = link
        if summary:
            raw_item["summary"] = summary
            raw_item["description"] = summary
        if content_text:
            raw_item["content_text"] = content_text
            raw_item["content_html"] = content_text
        if published_at:
            raw_item["date_published"] = published_at
            raw_item["published_at"] = published_at
        if news_id:
            raw_item["id"] = news_id

        if raw_item:
            items.append(raw_item)

    return items


def _normalize_feed_item(raw_item: dict, source_feed_url: str) -> dict | None:
    title = _strip_html(raw_item.get("title") or raw_item.get("name"))
    if not title:
        return None

    link = (
        raw_item.get("url")
        or raw_item.get("link")
        or raw_item.get("external_url")
        or raw_item.get("id")
    )
    if not isinstance(link, str):
        return None

    link = link.strip()
    if not link:
        return None

    summary_text = _strip_html(raw_item.get("summary") or raw_item.get("description"))
    content_text = _strip_html(
        raw_item.get("content_text") or raw_item.get("content_html")
    )
    content = content_text or summary_text or title
    outline = summary_text or content[:200]

    published_at = (
        raw_item.get("date_published")
        or raw_item.get("published_at")
        or raw_item.get("updated")
    )
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
    normalized_source = normalize_rsshub_source_url(source_url, feed_format="json")
    if not normalized_source:
        return []

    rss_source = normalize_rsshub_source_url(source_url, feed_format=None)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    def _request_feed(url: str) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(1, RSSHUB_FEED_RETRY_ATTEMPTS + 1):
            try:
                return requests.get(
                    url, headers=headers, timeout=RSSHUB_FEED_TIMEOUT_SECONDS
                )
            except _RETRYABLE_REQUEST_EXC as exc:
                # 瞬时错误：IncompleteRead / Connection broken / Timeout
                # RSSHub 公共实例经常中途断流，重试 1-2 次通常能拿到完整 body
                last_exc = exc
                if attempt >= RSSHUB_FEED_RETRY_ATTEMPTS:
                    break
                log_with_time(
                    f"[rsshub] 第 {attempt}/{RSSHUB_FEED_RETRY_ATTEMPTS} 次请求 {url} 失败（{type(exc).__name__}: {exc}），{RSSHUB_FEED_RETRY_BACKOFF_SECONDS}s 后重试",
                    "warn",
                )
                import time as _t

                _t.sleep(RSSHUB_FEED_RETRY_BACKOFF_SECONDS * attempt)
                continue
            except Exception as exc:  # 其它错误（DNS、连接拒绝等）直接抛
                raise RSSHubFetchError(
                    _describe_rsshub_request_error(exc, url),
                    source_url=source_url,
                    normalized_source_url=url,
                ) from exc
        # 全部重试用完仍失败
        assert last_exc is not None
        raise RSSHubFetchError(
            _describe_rsshub_request_error(
                last_exc, url, attempts=RSSHUB_FEED_RETRY_ATTEMPTS
            ),
            source_url=source_url,
            normalized_source_url=url,
        ) from last_exc

    response = _request_feed(normalized_source)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and status_code >= 400:
        if status_code == 403 and rss_source and rss_source != normalized_source:
            fallback_response = _request_feed(rss_source)
            fallback_status = getattr(fallback_response, "status_code", None)
            if isinstance(fallback_status, int) and fallback_status >= 400:
                raise RSSHubFetchError(
                    _describe_rsshub_status_error(
                        fallback_status,
                        rss_source,
                        body_snippet=getattr(fallback_response, "text", "")[:500]
                        or None,
                    ),
                    source_url=source_url,
                    normalized_source_url=rss_source,
                    status_code=fallback_status,
                )

            items = _extract_items_from_xml_payload(
                getattr(fallback_response, "text", "")
            )
            normalized_items: list[dict] = []
            max_items = max(limit, 0)

            for raw_item in items:
                normalized_item = _normalize_feed_item(raw_item, rss_source)
                if not normalized_item:
                    continue
                normalized_items.append(normalized_item)
                if max_items and len(normalized_items) >= max_items:
                    break

            return normalized_items

        raise RSSHubFetchError(
            _describe_rsshub_status_error(
                status_code,
                normalized_source,
                body_snippet=getattr(response, "text", "")[:200] or None,
            ),
            source_url=source_url,
            normalized_source_url=normalized_source,
            status_code=status_code,
        )

    try:
        payload = response.json()
    except Exception:
        if rss_source and rss_source != normalized_source:
            fallback_response = _request_feed(rss_source)
            fallback_status = getattr(fallback_response, "status_code", None)
            if isinstance(fallback_status, int) and fallback_status >= 400:
                raise RSSHubFetchError(
                    _describe_rsshub_status_error(
                        fallback_status,
                        rss_source,
                        body_snippet=getattr(fallback_response, "text", "")[:500]
                        or None,
                    ),
                    source_url=source_url,
                    normalized_source_url=rss_source,
                    status_code=fallback_status,
                )

            items = _extract_items_from_xml_payload(
                getattr(fallback_response, "text", "")
            )
            normalized_items: list[dict] = []
            max_items = max(limit, 0)

            for raw_item in items:
                normalized_item = _normalize_feed_item(raw_item, rss_source)
                if not normalized_item:
                    continue
                normalized_items.append(normalized_item)
                if max_items and len(normalized_items) >= max_items:
                    break

            return normalized_items

        raise RSSHubFetchError(
            f"RSSHub 返回了无效的 JSON 内容，请检查订阅源或 RSSHUB_BASE_URL：{normalized_source}",
            source_url=source_url,
            normalized_source_url=normalized_source,
            status_code=status_code if isinstance(status_code, int) else None,
        )

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
