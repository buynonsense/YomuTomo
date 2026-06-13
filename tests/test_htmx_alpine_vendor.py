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


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3a: AI 配置保存 → htmx 表单
# ─────────────────────────────────────────────────────────────────────────────


def test_ai_config_form_uses_htmx_post_in_modal():
    modal = (REPO_ROOT / "templates" / "partials" / "global_settings_modal.html").read_text(encoding="utf-8")
    # AI panel 内的表单必须是 htmx 表单
    assert 'id="ai-config-form"' in modal
    assert 'hx-post="/save_ai_config"' in modal
    assert 'hx-target="#ai-config-feedback"' in modal
    # 输入字段必须有 name，否则 form 序列化不到后端
    assert 'name="openai_api_key"' in modal
    assert 'name="openai_base_url"' in modal
    assert 'name="openai_model"' in modal
    # 保存按钮必须是 submit，交给 htmx 自动接管
    assert 'id="save-config"' in modal
    assert 'type="submit"' in modal
    # 反馈容器存在
    assert 'id="ai-config-feedback"' in modal


def test_ai_config_feedback_partial_has_success_and_error_branches():
    partial = (REPO_ROOT / "templates" / "partials" / "_ai_config_feedback.html").read_text(encoding="utf-8")
    assert "{% if success %}" in partial
    assert "{% else %}" in partial
    assert "is-success" in partial
    assert "is-error" in partial
    assert "AI 配置" in partial


def test_settings_modal_js_no_longer_binds_click_save_ai_config():
    """Stage 3a: save-config 不再绑 saveAiConfig，改为 type=submit + htmx 自提交。"""
    js = (REPO_ROOT / "static" / "js" / "modules" / "settings-modal.js").read_text(encoding="utf-8")
    # 旧的 click→saveAiConfig 链路已删除
    assert "saveConfigBtn.addEventListener('click', saveAiConfig)" not in js
    assert "async function saveAiConfig" not in js
    # 新链路：提交按钮 type=submit，由 htmx 接管
    assert "setAttribute('type', 'submit')" in js
    # 业务反馈走 HX-Trigger 派发的 ai-config-saved / ai-config-failed 事件
    assert "'ai-config-saved'" in js
    assert "'ai-config-failed'" in js
    assert "attachHtmxListeners" in js


class _StubAIClient:
    """替身 AIClient：跳过真实 chat，直接假装通过。"""

    last_chat: list | None = None

    def __init__(self, provider):
        self.provider = provider

    async def chat(self, messages):
        type(self).last_chat = messages
        return {"ok": True}


def test_save_ai_config_htmx_success_returns_fragment_and_trigger(client, db_session, monkeypatch):
    """htmx 请求保存成功：返回 partial + HX-Trigger: ai-config-saved。"""
    from app.model.models import User
    from app.routers import articles as articles_router
    from app.routers import auth, pages
    from app.services import services as service_module

    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")
    monkeypatch.setattr(auth, "is_legacy_bcrypt_hash", lambda hashed: False)
    monkeypatch.setattr(service_module, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service_module, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")

    user = User(
        email="stage3a-ok@example.com",
        password_hash="hashed:secret123",
        level=1,
        openai_api_key="",
        openai_base_url="",
        openai_model="",
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

    # 替身 AIClient.factory，避免真打远程 API
    from app.services import ai_client_async as ai_module

    monkeypatch.setattr(ai_module.AIClient, "factory", staticmethod(lambda provider: _StubAIClient(provider)))

    with client as c:
        c.post("/login", data={"email": "stage3a-ok@example.com", "password": "secret123"})
        resp = c.post(
            "/save_ai_config",
            data={
                "openai_api_key": "sk-stage3a",
                "openai_base_url": "https://api.example.com/v1",
                "openai_model": "gpt-4o-mini",
            },
            headers={"HX-Request": "true"},
        )

    assert resp.status_code == 200
    body = resp.text
    assert "is-success" in body
    assert "AI 配置已保存成功" in body
    assert "is-error" not in body

    import json as _json

    trigger = _json.loads(resp.headers["hx-trigger"])
    assert "ai-config-saved" in trigger
    assert trigger["ai-config-saved"]["message"] == "AI配置保存成功"

    # 落库断言
    db_session.refresh(user)
    assert user.openai_api_key == "sk-stage3a"
    assert user.openai_model == "gpt-4o-mini"


def test_save_ai_config_htmx_failure_returns_error_fragment(client, db_session, monkeypatch):
    """htmx 请求保存失败：返回 partial + HX-Trigger: ai-config-failed。"""
    from app.model.models import User
    from app.routers import articles as articles_router
    from app.routers import auth, pages
    from app.services import services as service_module

    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")
    monkeypatch.setattr(auth, "is_legacy_bcrypt_hash", lambda hashed: False)
    monkeypatch.setattr(service_module, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service_module, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")

    user = User(
        email="stage3a-fail@example.com",
        password_hash="hashed:secret123",
        level=1,
        openai_api_key="",
        openai_base_url="",
        openai_model="",
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

    class _BrokenAIClient(_StubAIClient):
        async def chat(self, messages):
            from app.services.ai_client_async import AIClientError

            raise AIClientError("remote 401 unauthorized")

    from app.services import ai_client_async as ai_module

    monkeypatch.setattr(ai_module.AIClient, "factory", staticmethod(lambda provider: _BrokenAIClient(provider)))

    with client as c:
        c.post("/login", data={"email": "stage3a-fail@example.com", "password": "secret123"})
        resp = c.post(
            "/save_ai_config",
            data={
                "openai_api_key": "sk-bad",
                "openai_base_url": "https://api.example.com/v1",
                "openai_model": "gpt-4o-mini",
            },
            headers={"HX-Request": "true"},
        )

    assert resp.status_code == 200
    body = resp.text
    assert "is-error" in body
    assert "401" in body
    assert "is-success" not in body

    import json as _json

    trigger = _json.loads(resp.headers["hx-trigger"])
    assert "ai-config-failed" in trigger
    assert "401" in trigger["ai-config-failed"]["message"]

    # 失败时不应落库
    db_session.refresh(user)
    assert user.openai_api_key == ""


def test_save_ai_config_non_htmx_request_still_returns_json(client, db_session, monkeypatch):
    """非 htmx 请求（非 XHR 场景）维持 JSON 响应，避免破坏其他调用方。"""
    from app.model.models import User
    from app.routers import articles as articles_router
    from app.routers import auth, pages
    from app.services import services as service_module

    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")
    monkeypatch.setattr(auth, "is_legacy_bcrypt_hash", lambda hashed: False)
    monkeypatch.setattr(service_module, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service_module, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")

    user = User(
        email="stage3a-json@example.com",
        password_hash="hashed:secret123",
        level=1,
        openai_api_key="",
        openai_base_url="",
        openai_model="",
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

    from app.services import ai_client_async as ai_module

    monkeypatch.setattr(ai_module.AIClient, "factory", staticmethod(lambda provider: _StubAIClient(provider)))

    with client as c:
        c.post("/login", data={"email": "stage3a-json@example.com", "password": "secret123"})
        resp = c.post(
            "/save_ai_config",
            data={
                "openai_api_key": "sk-x",
                "openai_base_url": "https://api.example.com/v1",
                "openai_model": "gpt-4o-mini",
            },
            # 不带 HX-Request 头
        )

    assert resp.status_code == 200
    body = resp.text
    # JSON 响应里 success 字段是 true，键值无空格
    assert '"success":true' in body or '"success": true' in body
    assert "AI配置保存成功" in body
    # 也没有 htmx 反馈片段特征
    assert "ai-config-feedback__inner" not in body


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3b: 生词掌握 toggle → hx-post 片段
# ─────────────────────────────────────────────────────────────────────────────


def test_vocab_toggle_partial_form_uses_htmx_and_carries_state():
    """toggle 片段必须包含 hx-post 表单，且 current_mastered/word 字段都要带上。"""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader("templates"))
    tpl = env.get_template("partials/_vocab_toggle_form.html")
    body = tpl.render(
        word="日本語",
        pronunciation="にほんご",
        meaning="日语",
        article_id=42,
        current_mastered=0,
    )
    assert 'class="vocab-toggle-form"' in body
    assert 'hx-post="/vocabulary/toggle"' in body
    assert 'hx-swap="outerHTML"' in body
    assert 'hx-target="this"' in body
    assert 'name="word" value="日本語"' in body
    assert 'name="pronunciation" value="にほんご"' in body
    assert 'name="meaning" value="日语"' in body
    assert 'name="article_id" value="42"' in body
    assert 'name="current_mastered" value="0"' in body
    # 当前未掌握 → 显示"已掌握"
    assert ">已掌握<" in body

    body_mastered = tpl.render(
        word="日本語",
        pronunciation="にほんご",
        meaning="日语",
        article_id=42,
        current_mastered=1,
    )
    # 当前已掌握 → 显示"取消掌握" + 按钮带 is-mastered
    assert ">取消掌握<" in body_mastered
    assert "is-mastered" in body_mastered


def test_reading_vocab_uses_htmx_form_for_toggle():
    reading = (REPO_ROOT / "templates" / "reading.html").read_text(encoding="utf-8")
    assert 'class="vocab-toggle-form"' in reading
    assert 'hx-post="/vocabulary/toggle"' in reading
    # 必须使用 hx-swap="outerHTML" + hx-target="this"，否则按钮无法原位替换
    assert 'hx-swap="outerHTML"' in reading
    assert 'hx-target="this"' in reading


def test_vocabulary_page_uses_htmx_form_for_toggle():
    vocab = (REPO_ROOT / "templates" / "vocabulary.html").read_text(encoding="utf-8")
    assert 'class="vocab-toggle-form"' in vocab
    assert 'hx-post="/vocabulary/toggle"' in vocab
    assert 'hx-swap="outerHTML"' in vocab
    assert 'hx-target="this"' in vocab


def test_reading_js_drops_manual_toggle_chain():
    """旧 fetch(JSON)+手改 class 链路已删除；新链路只保留 speak click + vocab-toggled 监听。"""
    js = (REPO_ROOT / "static" / "js" / "pages" / "reading.js").read_text(encoding="utf-8")
    # 函数定义 / 调用都已删除（注释里出现只是文档说明）
    assert "toggleVocabMastered(button)" not in js
    assert "persistVocabularyStatus(payload)" not in js
    # click 分支只剩 speak
    assert "speakVocabWord" in js
    # 新链路：vocab-toggled 事件 + .is-mastered 同步
    assert "vocab-toggled" in js
    assert "is-mastered" in js
    assert "bindVocabToggleSync" in js
    # cssEscape 防护：含特殊字符的 word 不会让 querySelectorAll 抛错
    assert "cssEscape" in js


def test_vocab_toggle_endpoint_htmx_returns_partial(client, db_session, monkeypatch):
    """htmx 请求 → 服务端返回 toggle form 片段 + HX-Trigger: vocab-toggled。"""
    from app.model.models import User, Article, VocabularyEntry
    from app.routers import articles as articles_router
    from app.routers import auth, pages
    from app.services import services as service_module

    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")
    monkeypatch.setattr(auth, "is_legacy_bcrypt_hash", lambda hashed: False)
    monkeypatch.setattr(service_module, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service_module, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")

    user = User(
        email="stage3b-ok@example.com",
        password_hash="hashed:secret123",
        level=1,
        openai_api_key="sk-test",
        openai_base_url="https://api.example.com/v1",
        openai_model="gpt-4o-mini",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    article = Article(
        user_id=user.id,
        title="t",
        original="x",
        translation="y",
        ruby_html="<ruby>x</ruby>",
        vocab_json="[]",
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    def current_user(request, db):
        uid = request.session.get("user_id")
        if not uid:
            return None
        return db.get(User, uid)

    monkeypatch.setattr(pages, "get_current_user", current_user)
    monkeypatch.setattr(auth, "get_current_user", current_user)
    monkeypatch.setattr(articles_router, "get_current_user", current_user)
    monkeypatch.setattr(articles_router, "require_login", current_user)

    with client as c:
        c.post("/login", data={"email": "stage3b-ok@example.com", "password": "secret123"})
        # 当前未掌握 → 这次点击要"标记为已掌握"
        resp = c.post(
            "/vocabulary/toggle",
            data={
                "word": "日本語",
                "pronunciation": "にほんご",
                "meaning": "日语",
                "article_id": str(article.id),
                "current_mastered": "0",
            },
            headers={"HX-Request": "true"},
        )

    assert resp.status_code == 200
    body = resp.text
    # 返回的是 form 片段
    assert 'class="vocab-toggle-form"' in body
    # 翻转后应当显示"取消掌握"
    assert ">取消掌握<" in body
    assert 'value="1"' in body  # current_mastered 现在是 1

    import json as _json

    trigger = _json.loads(resp.headers["hx-trigger"])
    assert trigger["vocab-toggled"]["word"] == "日本語"
    assert trigger["vocab-toggled"]["mastered"] is True

    # 落库
    entry = db_session.query(VocabularyEntry).filter_by(user_id=user.id, word="日本語").first()
    assert entry is not None
    assert entry.status == "mastered"


def test_vocab_toggle_endpoint_htmx_toggles_back(client, db_session, monkeypatch):
    """已掌握 → 再次 toggle 应当回到 unmastered。"""
    from app.model.models import User, Article, VocabularyEntry
    from app.routers import articles as articles_router
    from app.routers import auth, pages
    from app.services import services as service_module

    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")
    monkeypatch.setattr(auth, "is_legacy_bcrypt_hash", lambda hashed: False)
    monkeypatch.setattr(service_module, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service_module, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")

    user = User(
        email="stage3b-back@example.com",
        password_hash="hashed:secret123",
        level=1,
        openai_api_key="sk-test",
        openai_base_url="https://api.example.com/v1",
        openai_model="gpt-4o-mini",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    article = Article(
        user_id=user.id,
        title="t",
        original="x",
        translation="y",
        ruby_html="<ruby>x</ruby>",
        vocab_json="[]",
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    def current_user(request, db):
        uid = request.session.get("user_id")
        if not uid:
            return None
        return db.get(User, uid)

    monkeypatch.setattr(pages, "get_current_user", current_user)
    monkeypatch.setattr(auth, "get_current_user", current_user)
    monkeypatch.setattr(articles_router, "get_current_user", current_user)
    monkeypatch.setattr(articles_router, "require_login", current_user)

    with client as c:
        c.post("/login", data={"email": "stage3b-back@example.com", "password": "secret123"})
        # 第一次：标记为已掌握
        c.post(
            "/vocabulary/toggle",
            data={"word": "学校", "current_mastered": "0", "article_id": str(article.id)},
            headers={"HX-Request": "true"},
        )
        # 第二次：取消掌握
        resp = c.post(
            "/vocabulary/toggle",
            data={"word": "学校", "current_mastered": "1", "article_id": str(article.id)},
            headers={"HX-Request": "true"},
        )

    assert resp.status_code == 200
    body = resp.text
    assert ">已掌握<" in body
    assert 'value="0"' in body

    entry = db_session.query(VocabularyEntry).filter_by(user_id=user.id, word="学校").first()
    assert entry is not None
    assert entry.status != "mastered"


def test_vocab_toggle_endpoint_non_htmx_returns_json(client, db_session, monkeypatch):
    """非 htmx 请求维持 JSON 协议，不破坏其它客户端。"""
    from app.model.models import User
    from app.routers import articles as articles_router
    from app.routers import auth, pages
    from app.services import services as service_module

    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")
    monkeypatch.setattr(auth, "is_legacy_bcrypt_hash", lambda hashed: False)
    monkeypatch.setattr(service_module, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service_module, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")

    user = User(
        email="stage3b-json@example.com",
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

    with client as c:
        c.post("/login", data={"email": "stage3b-json@example.com", "password": "secret123"})
        resp = c.post(
            "/vocabulary/toggle",
            json={"word": "本", "mastered": True, "article_id": None},
        )

    assert resp.status_code == 200
    body = resp.text
    assert '"success":true' in body
    assert '"mastered":true' in body
    # 不是 form 片段
    assert "vocab-toggle-form" not in body

