"""Stage 1 基建验证：
- htmx 2.0.3 + alpine 3.13.10 vendor 资源能从 /static/vendor 200 返回
- 模板 partials/global_nav.html 注入了对应 <script> 标签
- HtmxRequestMiddleware 能正确解析 HX-Request / HX-Target / HX-Trigger 头
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from starlette.requests import Request

from app.main import HtmxRequestMiddleware


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_htmx_vendor_file_exists_and_is_minified():
    p = REPO_ROOT / "static" / "vendor" / "htmx.min.js"
    assert p.exists(), f"缺少 vendor 资源: {p}"
    text = p.read_text(encoding="utf-8", errors="ignore")
    # 必须没有真正的换行（minified 后一般是单行）
    assert "\n" not in text, "htmx 资源必须是 minified 单行"
    # 内容里要出现 htmx 特征标识
    assert "htmx" in text


def test_alpine_vendor_file_exists_and_is_minified():
    p = REPO_ROOT / "static" / "vendor" / "alpine.min.js"
    assert p.exists(), f"缺少 vendor 资源: {p}"
    text = p.read_text(encoding="utf-8", errors="ignore")
    # Alpine cdn.min.js 末尾可能含少量换行，宽松判断
    assert text.count("\n") <= 10, "alpine 资源必须是 minified（仅允许极少换行）"
    assert "Alpine" in text or "alpine" in text


def test_global_nav_includes_htmx_and_alpine_scripts():
    nav = (REPO_ROOT / "templates" / "partials" / "global_nav.html").read_text(encoding="utf-8")
    assert "/static/vendor/htmx.min.js" in nav
    assert "/static/vendor/alpine.min.js" in nav
    # 必须在 notifications.js 之前加载（保证后续 htmx-on 事件能被监听）
    htmx_pos = nav.find("/static/vendor/htmx.min.js")
    alpine_pos = nav.find("/static/vendor/alpine.min.js")
    notif_pos = nav.find("/static/js/modules/notifications.js")
    assert 0 <= htmx_pos < notif_pos
    assert 0 <= alpine_pos < notif_pos


def test_htmx_middleware_sets_state_flags():
    """HtmxRequestMiddleware 应该把 HX-* 头解析到 request.state 上。"""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "path": "/api/x",
        "raw_path": b"/api/x",
        "query_string": b"",
        "headers": [
            (b"hx-request", b"true"),
            (b"hx-target", b"queue-list"),
            (b"hx-trigger", b"load"),
            (b"hx-trigger-name", b""),
            (b"hx-current-url", b"http://127.0.0.1:8000/news_center"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
        "scheme": "http",
    }
    request = Request(scope)
    captured = {}

    async def call_next(req):
        captured["state"] = req.state
        return _FakeResponse()

    class _FakeResponse:
        pass

    mw = HtmxRequestMiddleware(app=None)
    asyncio.run(mw.dispatch(request, call_next))
    state = captured["state"]
    assert state.htmx is True
    assert state.htmx_target == "queue-list"
    assert state.htmx_trigger == "load"
    assert state.htmx_trigger_name == ""
    assert state.htmx_current_url == "http://127.0.0.1:8000/news_center"


def test_htmx_middleware_off_when_header_missing():
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
    request = Request(scope)
    captured = {}

    async def call_next(req):
        captured["state"] = req.state
        return _FakeResponse()

    class _FakeResponse:
        pass

    mw = HtmxRequestMiddleware(app=None)
    asyncio.run(mw.dispatch(request, call_next))
    state = captured["state"]
    assert state.htmx is False
    assert state.htmx_target == ""
    assert state.htmx_trigger == ""


@pytest.mark.parametrize("header_value", ["true", "True", "TRUE", "1"])
def test_htmx_middleware_accepts_loose_true(header_value):
    """HX-Request 头应当对大小写宽松（htmx 默认小写，但其它客户端可能发大写）。"""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [(b"hx-request", header_value.encode("ascii"))],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
        "scheme": "http",
    }
    request = Request(scope)
    captured = {}

    async def call_next(req):
        captured["state"] = req.state
        return _FakeResponse()

    class _FakeResponse:
        pass

    mw = HtmxRequestMiddleware(app=None)
    asyncio.run(mw.dispatch(request, call_next))
    # 我们显式走 .lower() == 'true'，因此 "1" 不会被认作 true。
    # 这是 htmx 协议兼容行为；非 'true' 视为非 htmx。
    if header_value.lower() == "true":
        assert captured["state"].htmx is True
    else:
        assert captured["state"].htmx is False
