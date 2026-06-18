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
    # Stage 2 把爬取队列的轮询迁到了 htmx 片段，所以这里至少还有 2 处 response.ok
    # （自定义订阅源预览 + 多选批量提交）
    assert news_center_js.count("response.ok") >= 2
    assert "window.Utils.formatDateTime" in news_center_js
    assert "data-news-published-at" in news_center_js


def test_dashboard_template_uses_timestamp_data_attribute():
    from pathlib import Path

    dashboard_html = Path("templates/dashboard.html").read_text(encoding="utf-8")
    assert "data-article-updated-at" in dashboard_html
    assert "updated_at_beijing" not in dashboard_html
    assert "updated_at_iso" in dashboard_html


def test_dashboard_script_formats_article_timestamps_locally():
    from pathlib import Path

    dashboard_js = Path("static/js/pages/dashboard.js").read_text(encoding="utf-8")
    assert "data-article-updated-at" in dashboard_js
    assert "window.Utils.formatDateTime" in dashboard_js
    assert "toLocaleString" not in dashboard_js


def test_notifications_script_formats_times_through_shared_helper():
    from pathlib import Path

    notifications_js = Path("static/js/modules/notifications.js").read_text(encoding="utf-8")
    assert "window.Utils.formatDateTime" in notifications_js
    assert "toLocaleString" not in notifications_js


def test_vocabulary_script_formats_times_through_shared_helper():
    from pathlib import Path

    vocabulary_js = Path("static/js/pages/vocabulary.js").read_text(encoding="utf-8")
    assert "window.Utils.formatDateTime" in vocabulary_js
    assert "toLocaleString" not in vocabulary_js


def test_pdf_export_uses_shared_datetime_formatter():
    from pathlib import Path

    pdf_export_js = Path("static/js/modules/pdf-export.js").read_text(encoding="utf-8")
    assert "window.Utils.formatDateTime" in pdf_export_js
    assert "formatFilenameDate" in pdf_export_js
    assert "toLocaleString" not in pdf_export_js


def test_vocabulary_page_marks_timestamps_for_client_side_formatting():
    from pathlib import Path

    vocabulary_html = Path("templates/vocabulary.html").read_text(encoding="utf-8")
    assert "data-vocab-mastered-at" in vocabulary_html
    assert "掌握时间：</div>" in vocabulary_html


def test_news_center_template_marks_published_at_for_client_side_formatting():
    from pathlib import Path

    news_center_html = Path("templates/news_center.html").read_text(encoding="utf-8")
    assert "data-news-published-at" in news_center_html
    assert "data-news-published-at-display" in news_center_html


def test_safe_href_filter_is_available_for_template_links():
    from app.utils.templates import create_templates

    templates = create_templates()
    assert "safe_href" in templates.env.filters
    assert templates.env.filters["safe_href"]("/dashboard?foo=1") == "/dashboard?foo=1"
    assert templates.env.filters["safe_href"]("javascript:alert(1)") == "#"
    assert templates.env.filters["safe_href"]("https://example.com/path") == "https://example.com/path"
