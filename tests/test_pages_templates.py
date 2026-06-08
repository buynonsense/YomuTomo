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


def test_global_notifications_panel_template_exists():
    from pathlib import Path

    assert Path("templates/partials/global_notifications_panel.html").exists()


def test_global_nav_contains_notification_button_and_panel():
    from pathlib import Path

    nav_text = Path("templates/partials/global_nav.html").read_text(encoding="utf-8")
    assert "global-notifications-btn" in nav_text
    assert "global-notifications-badge" in nav_text
    assert "global_notifications_panel.html" in nav_text


def test_news_center_checks_status_response_ok():
    from pathlib import Path

    news_center_js = Path("static/js/pages/news-center.js").read_text(encoding="utf-8")
    assert news_center_js.count("response.ok") >= 3
