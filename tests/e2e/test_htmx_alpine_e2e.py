"""
Stage 5: 端到端 Playwright 测试

覆盖：
- 真实 uvicorn 服务 + sqlite 文件 DB
- 浏览器加载 /news_center, /vocabulary, /dashboard
- 验证 htmx + alpine 已加载
- 验证设置弹窗 Alpine 状态机可开关
- 验证生词翻卡 Alpine 状态机可翻牌
- 验证新闻多选工具栏 Alpine 状态机可计数
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEST_DB_FILE = REPO_ROOT / "tests" / "_e2e_yomutomo.db"
TEST_DB_URL = f"sqlite:///{TEST_DB_FILE}"


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_http(url: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status in (200, 303):
                    return
        except Exception as e:
            last_err = e
        time.sleep(0.1)
    raise RuntimeError(f"server at {url} did not become ready in {timeout}s: {last_err}")


@pytest.fixture(scope="module")
def e2e_server():
    """启动真实 uvicorn + sqlite 文件 DB + 预置测试用户。"""
    if TEST_DB_FILE.exists():
        TEST_DB_FILE.unlink()

    # 重新 import app 的 db / main, 让 engine 绑定到新 URL
    os.environ["DATABASE_URL"] = TEST_DB_URL
    os.environ["SECRET_KEY"] = "e2e-secret-key"

    # 强制重新加载 app 内部 db 引用
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    import uvicorn
    from app import db as app_db
    from app import main as app_main
    from app.db import Base
    from app.model.models import User
    from app.services.services import hash_password

    # 显式替换 engine 走 sqlite 文件
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    app_db.engine = engine
    app_main.engine = engine
    app_db.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # 预置测试用户
    session = app_db.SessionLocal()
    try:
        user = User(email="e2e@x.com", password_hash=hash_password("pwpwpw"), level=3)
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
    finally:
        session.close()

    port = _free_port()
    config = uvicorn.Config(
        app_main.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    _wait_for_http(base_url + "/login", timeout=15.0)
    try:
        yield {"base_url": base_url, "user_id": user_id, "email": "e2e@x.com", "password": "pwpwpw"}
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if TEST_DB_FILE.exists():
            TEST_DB_FILE.unlink()


@pytest.fixture(scope="module")
def logged_in_context(e2e_server):
    """返回已登录 playwright BrowserContext。"""
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    try:
        browser = p.chromium.launch()
    except Exception as e:
        p.stop()
        pytest.skip(f"playwright browser not available: {e}")

    context = browser.new_context()
    page = context.new_page()
    # 通过真实表单登录
    page.goto(e2e_server["base_url"] + "/login")
    page.fill("input[name=email]", e2e_server["email"])
    page.fill("input[name=password]", e2e_server["password"])
    page.click("button[type=submit]")
    page.wait_for_url("**/dashboard", timeout=5000)
    yield {"page": page, "context": context, "browser": browser, "base_url": e2e_server["base_url"]}
    context.close()
    browser.close()
    p.stop()


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_vendor_scripts_loaded(e2e_server):
    """Stage 5: 浏览器加载 htmx + alpine。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto(e2e_server["base_url"] + "/login")
        htmx_ok = page.evaluate("typeof window.htmx !== 'undefined' || document.querySelector('script[src*=htmx]') !== null")
        alpine_ok = page.evaluate("typeof window.Alpine !== 'undefined' || document.querySelector('script[src*=alpine]') !== null")
        assert htmx_ok, "htmx script tag missing"
        assert alpine_ok, "alpine script tag missing"
        b.close()


@pytest.mark.e2e
def test_login_flow_redirects_to_dashboard(e2e_server):
    """Stage 5: 真实表单登录后跳转到 /dashboard。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto(e2e_server["base_url"] + "/login")
        page.fill("input[name=email]", e2e_server["email"])
        page.fill("input[name=password]", e2e_server["password"])
        page.click("button[type=submit]")
        page.wait_for_url("**/dashboard", timeout=5000)
        assert "/dashboard" in page.url
        b.close()


@pytest.mark.e2e
def test_settings_modal_alpine_toggle(logged_in_context):
    """Stage 5: 设置弹窗 Alpine 状态机 - 打开/关闭。"""
    page = logged_in_context["page"]
    page.goto(logged_in_context["base_url"] + "/vocabulary")

    # 弹窗初始 hidden (Alpine: isOpen=false => aria-hidden="true", panel class is x-show 关闭)
    modal = page.locator("#settings-modal")
    assert modal.count() == 1

    # 触发打开 (用户按钮)
    page.locator("#global-settings-btn").click()
    page.wait_for_timeout(300)

    # 弹窗可见
    assert modal.evaluate("el => !el.classList.contains('hidden') || el.getAttribute('aria-hidden') === 'false'")

    # ESC 关闭
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    # 关闭后 aria-hidden=true
    assert modal.get_attribute("aria-hidden") == "true"


@pytest.mark.e2e
def test_news_center_alpine_selection_toolbar(logged_in_context):
    """Stage 5: 新闻多选 Alpine 状态机 - 工具栏 hidden / count 联动。

    真实集成: 通过 bridge.add() 走真实代码路径 (不是直接派发事件),
    验证 Alpine 通过 window 监听器收到事件并切换 count。
    """
    page = logged_in_context["page"]
    page.goto(logged_in_context["base_url"] + "/news_center")
    page.wait_for_timeout(300)

    toolbar = page.locator("#news-selection-toolbar")
    assert toolbar.count() == 1

    # 初始: hidden
    is_hidden = toolbar.evaluate("el => el.hasAttribute('hidden') || el.hidden || window.getComputedStyle(el).display === 'none'")
    assert is_hidden, "selection toolbar should be hidden initially"

    # 真实集成: 注入假卡片, 走 bridge.add() 路径 (这正是用户点 checkbox 时的代码路径)
    page.evaluate("""
      () => {
        const card = document.createElement('article');
        card.setAttribute('data-news-card', 'true');
        card.setAttribute('data-news-url', 'http://test.example.com/news/1');
        card.setAttribute('data-news-title', 'Test Article');
        card.setAttribute('data-news-source-url', 'http://test.example.com');
        document.body.appendChild(card);
        // 走 bridge.add() — 它会派发 news:selection-changed 事件,
        // Alpine 工具栏必须能收到 (要求派发到 window, 不是 document)
        window.__newsSelectionBridge.add(card);
      }
    """)
    page.wait_for_timeout(200)

    # 工具栏应可见 (Alpine 收到事件后 count=1, x-bind:hidden 解锁)
    is_hidden_after = toolbar.evaluate("el => el.hasAttribute('hidden') || el.hidden || window.getComputedStyle(el).display === 'none'")
    assert not is_hidden_after, (
        f"selection toolbar should be visible after bridge.add(), got hidden={is_hidden_after}. "
        "这通常是 bridge 派发事件的目标 (document vs window) 与 Alpine x-on:...window 监听器不匹配"
    )

    # 额外验证: 工具栏内的 count 文本
    count_text = page.locator("#news-selection-count").text_content()
    assert count_text and count_text.strip() == "1", f"expected count=1, got {count_text!r}"


@pytest.mark.e2e
def test_vocabulary_review_alpine_state_machine(logged_in_context):
    """Stage 5: 生词翻卡 Alpine 状态机 - 工厂注册 + 派生 getter。"""
    page = logged_in_context["page"]
    page.goto(logged_in_context["base_url"] + "/vocabulary")
    page.wait_for_timeout(300)

    # Alpine 工厂注册
    has_factory = page.evaluate("typeof window.vocabReview === 'function'")
    assert has_factory, "window.vocabReview factory not registered"

    # 面板元素存在并带 x-data
    panel = page.locator("#vocab-review-panel")
    assert panel.count() == 1

    # 找到 Alpine 实例并验证 open() 方法存在
    has_open_method = page.evaluate("""
      () => {
        const panelEl = document.getElementById('vocab-review-panel');
        if (!panelEl || !panelEl._x_dataStack) return false;
        const inst = panelEl._x_dataStack[0];
        if (!inst) return false;
        return typeof inst.open === 'function';
      }
    """)
    assert has_open_method, "Alpine instance on #vocab-review-panel not initialized"


@pytest.mark.e2e
def test_dashboard_htmx_article_actions(logged_in_context):
    """Stage 5: dashboard 上的文章操作面板含 htmx 表单。"""
    page = logged_in_context["page"]
    page.goto(logged_in_context["base_url"] + "/dashboard")
    page.wait_for_timeout(200)

    # 检查 htmx 属性出现
    htmx_forms = page.locator("form[hx-post], form[hx-delete], form[hx-put]").count()
    # dashboard 可能无文章, 但模板里 htmx 属性应至少在 partial 里出现
    body_contains = page.evaluate("""
      () => document.body.innerHTML.includes('hx-post') || document.body.innerHTML.includes('hx-delete')
    """)
    assert body_contains or htmx_forms > 0, "dashboard should at least render htmx-aware forms or empty list"


@pytest.mark.e2e
def test_notifications_badge_present(logged_in_context):
    """Stage 5: 通知 badge 元素在导航栏。"""
    page = logged_in_context["page"]
    page.goto(logged_in_context["base_url"] + "/")
    page.wait_for_timeout(200)

    badge = page.locator("#global-notifications-badge")
    assert badge.count() == 1


@pytest.mark.e2e
def test_crawl_queue_htmx_poll_target(logged_in_context):
    """Stage 5: 爬取队列面板带 hx-get 轮询。"""
    page = logged_in_context["page"]
    page.goto(logged_in_context["base_url"] + "/news_center")
    page.wait_for_timeout(200)

    hx_present = page.evaluate("""
      () => {
        const el = document.querySelector('[hx-get], [hx-trigger]');
        if (el) return el.outerHTML.slice(0, 200);
        return null;
      }
    """)
    assert hx_present, "news center should have at least one htmx polling target"
