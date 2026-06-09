from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.services.ai_client_async import AIClientError, GeminiClient, OpenAICompatClient
from app.services import ai_client_async
from spider.rsshub_spider import generate_simplified_article, get_article_content


class FakeResponse:
    def __init__(self, payload, status_code: int = 200, url: str = "https://example.com/v1/chat/completions"):
        self._payload = payload
        self.status_code = status_code
        self.url = url
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", self.url)
            raise httpx.HTTPStatusError(f"{self.status_code} error", request=request, response=self)


class SequencedAsyncClient:
    def __init__(self, steps, timeout=None):
        self.steps = list(steps)
        self.timeout = timeout
        self.calls = 0
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None, params=None):
        self.requests.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "params": params,
            }
        )
        if self.calls >= len(self.steps):
            raise AssertionError("unexpected extra request")
        step = self.steps[self.calls]
        self.calls += 1
        if isinstance(step, Exception):
            raise step
        return step


def _timeout_exc(url: str) -> httpx.ReadTimeout:
    request = httpx.Request("POST", url)
    return httpx.ReadTimeout("read timed out", request=request)


def _openai_payload():
    return {"choices": [{"message": {"content": "ok"}}]}


def _gemini_payload():
    return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}


def test_openai_and_gemini_retry_once_then_succeed(monkeypatch):
    cases = [
        (
            OpenAICompatClient,
            {"api_url": "https://example.com/v1", "api_key": "sk-test", "model": "gpt-test"},
            _openai_payload(),
            "ok",
        ),
        (
            GeminiClient,
            {
                "api_url": "https://generativelanguage.googleapis.com",
                "api_key": "gemini-key",
                "model": "gemini-test",
            },
            _gemini_payload(),
            "ok",
        ),
    ]

    async def no_sleep(_seconds):
        return None

    for client_cls, provider, payload, expected_text in cases:
        monkeypatch.setattr(ai_client_async.settings, "AI_REQUEST_TIMEOUT_SECONDS", 12.5)
        monkeypatch.setattr(ai_client_async.settings, "AI_REQUEST_RETRIES", 2)
        monkeypatch.setattr(ai_client_async.settings, "AI_REQUEST_RETRY_DELAY_SECONDS", 0.0)
        monkeypatch.setattr(ai_client_async.asyncio, "sleep", no_sleep)

        fake_client = SequencedAsyncClient(
            steps=[
                _timeout_exc("https://example.com"),
                FakeResponse(payload),
            ],
        )
        captured = {}

        def fake_async_client(timeout=None):
            captured["timeout"] = timeout
            return fake_client

        monkeypatch.setattr(ai_client_async.httpx, "AsyncClient", fake_async_client)

        client = client_cls(provider)
        result = asyncio.run(client.chat([{"role": "user", "content": "hello"}]))

        assert result["text"] == expected_text
        assert fake_client.calls == 2
        assert captured["timeout"] == 12.5


def test_openai_timeout_exhaustion_raises_clean_error(monkeypatch):
    monkeypatch.setattr(ai_client_async.settings, "AI_REQUEST_TIMEOUT_SECONDS", 7.0)
    monkeypatch.setattr(ai_client_async.settings, "AI_REQUEST_RETRIES", 2)
    monkeypatch.setattr(ai_client_async.settings, "AI_REQUEST_RETRY_DELAY_SECONDS", 0.0)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(ai_client_async.asyncio, "sleep", no_sleep)

    fake_client = SequencedAsyncClient(
        steps=[
            _timeout_exc("https://example.com/v1/chat/completions"),
            _timeout_exc("https://example.com/v1/chat/completions"),
        ],
    )
    captured = {}
    exception_calls = []

    def fake_async_client(timeout=None):
        captured["timeout"] = timeout
        return fake_client

    monkeypatch.setattr(ai_client_async.httpx, "AsyncClient", fake_async_client)
    monkeypatch.setattr(ai_client_async.logger, "exception", lambda *args, **kwargs: exception_calls.append((args, kwargs)))

    client = OpenAICompatClient({"api_url": "https://example.com/v1", "api_key": "sk-test", "model": "gpt-test"})

    with pytest.raises(AIClientError, match="超时"):
        asyncio.run(client.chat([{"role": "user", "content": "hello"}]))

    assert fake_client.calls == 2
    assert captured["timeout"] == 7.0
    assert exception_calls == []


def test_generate_simplified_article_falls_back_to_original_text():
    class RaisingCompletions:
        def create(self, *args, **kwargs):
            raise AIClientError("read timed out")

    class RaisingClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": RaisingCompletions()})()

    original = "今日は天気です"
    result = generate_simplified_article(original, 3, "gpt-test", RaisingClient())

    assert result == original


def test_get_article_content_returns_none_when_fetch_fails(monkeypatch):
    monkeypatch.setattr("app.services.rsshub_feed.requests.get", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("read timed out")))

    assert get_article_content("https://example.com/news/1") is None


def test_get_article_content_reads_rsshub_json_feed(monkeypatch):
    source_url = "rsshub://example/news_feed"
    feed_url = "https://rsshub.app/example/news_feed?format=json"

    class Response:
        status_code = 200
        text = ""
        url = feed_url
        encoding = None

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "items": [
                    {
                        "title": "安定的な皇位継承 とりまとめ案報告の協議終わる",
                        "summary": "安定的な皇位継承をめぐり、衆参両院の議長・副議長と各党・各会派との協議が行われました。",
                        "url": "https://example.com/news/1",
                        "id": "news-1",
                    }
                ]
            }

    def fake_get(url, headers=None, timeout=None):
        if url == feed_url:
            return Response()
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("app.services.rsshub_feed.requests.get", fake_get)

    result = get_article_content(source_url)

    assert result is not None
    assert "安定的な皇位継承" in result


def test_get_article_content_strips_html_from_rsshub_feed(monkeypatch):
    source_url = "rsshub://example/news_feed"
    feed_url = "https://rsshub.app/example/news_feed?format=json"

    class Response:
        status_code = 200
        text = ""
        url = feed_url
        encoding = None

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "items": [
                    {
                        "title": "安定的な皇位継承 とりまとめ案報告の協議終わる",
                        "content_html": "<p>安定的な皇位継承をめぐり、<strong>衆参両院</strong>の議長・副議長と各党・各会派との協議が行われました。</p>",
                        "url": "https://example.com/news/1",
                        "id": "news-1",
                    }
                ]
            }

    def fake_get(url, headers=None, timeout=None):
        if url == feed_url:
            return Response()
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("app.services.rsshub_feed.requests.get", fake_get)

    result = get_article_content(source_url)

    assert result is not None
    assert "<" not in result
    assert "衆参両院" in result
