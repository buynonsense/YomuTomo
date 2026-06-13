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


# -----------------------------------------------------------------------------
# Stage 2: 爬取队列 + 通知未读数 → htmx 轮询
# -----------------------------------------------------------------------------


def test_crawl_queue_partial_template_exists():
    """hxp partial 必须存在，并且自身就带 htmx 自轮询属性。"""
    p = REPO_ROOT / "templates" / "partials" / "_crawl_queue_body.html"
    assert p.exists(), f"缺少 partial 模板: {p}"
    text = p.read_text(encoding="utf-8")
    # 整个 section 是 swap target
    assert 'id="crawl-queue-panel"' in text
    assert 'hx-get="/crawl_queue/partial"' in text
    assert 'hx-trigger' in text
    assert 'hx-swap="outerHTML"' in text
    # 有任务时不应隐藏
    assert "进行中" in text
    assert "最近完成" in text


def test_format_datetime_filter_renders_beijing_string():
    """Jinja2 filter format_datetime 必须把 datetime 转成北京时间 'YYYY-MM-DD HH:MM'。"""
    from datetime import datetime, timezone

    from app.utils.templates import create_templates

    tpl = create_templates("templates")
    # 2026-06-13 00:30 UTC = 2026-06-13 08:30 北京时间
    value = datetime(2026, 6, 13, 0, 30, tzinfo=timezone.utc)
    rendered = tpl.env.from_string("{{ value | format_datetime }}").render(value=value)
    assert rendered == "2026-06-13 08:30"

    # None / 无 tz 都应该安全降级成空串
    rendered_none = tpl.env.from_string("[{{ value | format_datetime }}]").render(value=None)
    assert rendered_none == "[]"


def test_task_progress_percent_global():
    from types import SimpleNamespace

    from app.utils.templates import create_templates

    tpl = create_templates("templates")
    # 有 total：按比例
    t1 = SimpleNamespace(total_articles=4, processed_articles=1, status="processing")
    t2 = SimpleNamespace(total_articles=4, processed_articles=4, status="completed")
    t3 = SimpleNamespace(total_articles=0, processed_articles=0, status="processing")
    t4 = SimpleNamespace(total_articles=0, processed_articles=0, status="pending")
    assert tpl.env.from_string("{{ task_progress_percent(t) }}").render(t=t1) == "25"
    assert tpl.env.from_string("{{ task_progress_percent(t) }}").render(t=t2) == "100"
    assert tpl.env.from_string("{{ task_progress_percent(t) }}").render(t=t3) == "5"
    assert tpl.env.from_string("{{ task_progress_percent(t) }}").render(t=t4) == "0"


def test_crawl_queue_partial_endpoint_unauthenticated_returns_empty(client):
    """未登录时仍然返回 200 + 空状态片段，避免 htmx 反复重试。"""
    resp = client.get("/crawl_queue/partial")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "暂无爬取任务" in body
    # 没有登录，所以面板应当处于 hidden 状态
    assert "hidden" in body
    # HX-Trigger 头里 activeCount == 0
    import json as _json

    trigger = _json.loads(resp.headers["hx-trigger"])
    assert trigger == {"queue-update": {"activeCount": 0}}


def test_crawl_queue_partial_endpoint_with_active_task(client, db_session, monkeypatch):
    """有活跃任务时，片段里要出现该任务，且 HX-Trigger 报告 activeCount > 0。"""
    from app.model.models import CrawlTask, User
    from app.routers import articles as articles_router
    from app.routers import auth, pages
    from app.services import services as service_module

    # auth.py 用 from-import 把 verify_password 拷到了自己命名空间，必须直接 patch
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")
    monkeypatch.setattr(auth, "is_legacy_bcrypt_hash", lambda hashed: False)
    monkeypatch.setattr(service_module, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service_module, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")

    user = User(
        email="stage2@example.com",
        password_hash="hashed:secret123",
        level=1,
        openai_api_key="sk-test",
        openai_base_url="https://api.example.com/v1",
        openai_model="gpt-4o-mini",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    def current_user(request, db):
        uid = request.session.get("user_id")
        if not uid:
            return None
        return db.get(User, uid)

    monkeypatch.setattr(pages, "get_current_user", current_user)
    monkeypatch.setattr(auth, "get_current_user", current_user)
    monkeypatch.setattr(articles_router, "get_current_user", current_user)
    monkeypatch.setattr(articles_router, "require_login", current_user)

    task = CrawlTask(
        user_id=user.id,
        status="processing",
        total_articles=4,
        processed_articles=2,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    with client as c:
        c.post("/login", data={"email": "stage2@example.com", "password": "secret123"})
        resp = c.get("/crawl_queue/partial")

    assert resp.status_code == 200
    body = resp.text
    assert f"任务 #{task.id}" in body
    assert "进行中" in body
    # 50% 进度（2/4）
    assert "2 / 4 篇" in body
    # 应当不再 hidden
    assert ">暂无爬取任务<" not in body

    import json as _json

    trigger = _json.loads(resp.headers["hx-trigger"])
    assert trigger["queue-update"]["activeCount"] == 1


def test_news_center_template_uses_htmx_panel():
    """news_center.html 必须用 htmx 自加载而不是手写 list 节点。"""
    tpl = (REPO_ROOT / "templates" / "news_center.html").read_text(encoding="utf-8")
    assert 'id="crawl-queue-panel"' in tpl
    assert 'hx-get="/crawl_queue/partial"' in tpl
    assert 'hx-trigger="load delay:200ms, every 2s"' in tpl
    assert 'hx-swap="outerHTML"' in tpl
    # 不再依赖手写的 list / count / empty 节点
    assert 'id="crawl-queue-list"' not in tpl
    assert 'id="crawl-queue-count"' not in tpl
    assert 'id="crawl-queue-empty"' not in tpl
    assert 'id="crawl-queue-meta"' not in tpl


def test_news_center_js_drops_poll_timer_and_dom_rendering():
    """Stage 2 把 setInterval / DOM 拼接从 news-center.js 全部移除。"""
    js = (REPO_ROOT / "static" / "js" / "pages" / "news-center.js").read_text(encoding="utf-8")
    for token in [
        "pollTimer",
        "startPolling",
        "stopPolling",
        "refreshQueue",
        "fetchQueue",
        "renderQueue",
        "createQueueItem",
        "taskStatusLabel",
        "taskProgressPercent",
        "setQueuePanelState",
        "queueList",
        "queueCount",
        "queueMeta",
        "queueEmpty",
        "queuePanel",
    ]:
        assert token not in js, f"news-center.js 不应再含 {token!r}（已迁到 htmx partial）"


def test_task_state_listens_to_htmx_queue_update():
    """task-state.js 必须在 htmx 派发 queue-update 时同步更新导航繁忙态。"""
    js = (REPO_ROOT / "static" / "js" / "modules" / "task-state.js").read_text(encoding="utf-8")
    assert "queue-update" in js
    assert "activeCount" in js
    # 事件回调必须调用 updateNewsNavBusy（保持导航项 is-busy class 与服务端一致）
    assert "updateNewsNavBusy" in js
