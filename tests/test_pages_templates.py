from __future__ import annotations

import asyncio
from types import SimpleNamespace

from starlette.requests import Request

from app.routers import pages


def make_request() -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
        "scheme": "http",
    }
    return Request(scope)


def test_home_uses_request_first_template_response(monkeypatch):
    captured = {}

    class FakeTemplates:
        def TemplateResponse(self, request, name, context=None):
            captured["request"] = request
            captured["name"] = name
            captured["context"] = context or {}
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr(pages, "templates", FakeTemplates())
    monkeypatch.setattr(pages, "get_current_user", lambda request, db: None)

    result = asyncio.run(pages.home(make_request(), db=SimpleNamespace()))

    assert result.status_code == 200
    assert captured["name"] == "index.html"
    assert captured["request"].scope["path"] == "/"
    assert captured["context"]["user"] is None
