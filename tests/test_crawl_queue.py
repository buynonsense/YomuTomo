from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.model.models import CrawlTask, User
from app.routers import articles as articles_router
import spider.rsshub_spider as spider_module


class _DummySyncClient:
    def __init__(self, text: str = "ok"):
        self.text = text
        self.chat = self
        self.completions = self

    def create(self, *args, **kwargs):
        return type(
            "Resp",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "message": type("Message", (), {"content": self.text})(),
                        },
                    )()
                ]
            },
        )()


class _DummyAsyncClient:
    async def chat(self, messages=None, extra=None):
        return {"text": "ok"}


@pytest.fixture(autouse=True)
def _fast_passwords(monkeypatch: pytest.MonkeyPatch):
    from app.services import services as service_module

    monkeypatch.setattr(service_module, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service_module, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")


@pytest.fixture()
def user_factory(db_session):
    def _make_user(
        email: str = "queue@example.com",
        password_hash: str = "hashed:secret123",
        level: int = 1,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            level=level,
            openai_api_key="sk-test",
            openai_base_url="https://api.example.com/v1",
            openai_model="gpt-4o-mini",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make_user


@pytest.fixture()
def queue_client(client: TestClient, db_session, monkeypatch: pytest.MonkeyPatch):
    from app import main as app_main
    from app.db import get_db
    from app.routers import auth, evaluation, pages
    from app.services import services as service_module

    def current_user(request, db):
        user_id = request.session.get("user_id")
        if not user_id:
            return None
        return db.get(User, user_id)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    monkeypatch.setattr(pages, "get_current_user", current_user)
    monkeypatch.setattr(auth, "get_current_user", current_user)
    monkeypatch.setattr(auth, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")
    monkeypatch.setattr(articles_router, "get_current_user", current_user)
    monkeypatch.setattr(articles_router, "require_login", current_user)
    monkeypatch.setattr(articles_router, "get_openai_client", lambda api_key, base_url: _DummySyncClient())
    monkeypatch.setattr(
        articles_router,
        "log_with_time",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(articles_router.AIClient, "factory", staticmethod(lambda provider: _DummyAsyncClient()))
    monkeypatch.setattr(service_module, "get_openai_client", lambda api_key, base_url: _DummySyncClient())
    monkeypatch.setattr(evaluation, "normalize_to_hiragana", lambda text: text)

    # 拦截 spider 启动，改为同步建任务，模拟后台执行
    def _fake_crawl(user_id: int, *args, **kwargs):
        url_list = list(kwargs.get("selected_urls") or [])
        # kwargs may also carry source_url etc.
        task = CrawlTask(
            user_id=user_id,
            status="pending",
            total_articles=len(url_list),
            processed_articles=0,
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        return {
            "success": True,
            "message": "ok",
            "task_id": task.id,
            "selected_urls": url_list,
        }

    monkeypatch.setattr(spider_module, "crawl_and_save_articles", _fake_crawl)
    monkeypatch.setattr(spider_module, "crawl_custom_url", _fake_crawl)

    app_main.app.dependency_overrides[get_db] = override_get_db
    yield client
    app_main.app.dependency_overrides.clear()


def _login(client: TestClient, email: str, password: str = "secret123"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def test_crawl_queue_requires_login(queue_client: TestClient):
    resp = queue_client.get("/crawl_queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("error") == "未登录"
    assert body["active"] == [] and body["recent"] == []


def test_crawl_queue_empty(queue_client: TestClient, user_factory):
    user_factory()
    _login(queue_client, "queue@example.com")
    body = queue_client.get("/crawl_queue").json()
    assert body["active"] == []
    assert body["recent"] == []
    assert body["counts"] == {"active": 0}


def test_crawl_news_accepts_multiple_urls(
    queue_client: TestClient, user_factory, db_session
):
    user_factory()
    _login(queue_client, "queue@example.com")

    resp = queue_client.post(
        "/crawl_news",
        json={
            "source_url": "https://rsshub.rssforever.com/nhk/news_web_easy",
            "selected_urls": [
                "https://example.com/a",
                "https://example.com/b",
                "https://example.com/c",
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["task_id"]

    queue = queue_client.get("/crawl_queue").json()
    assert len(queue["active"]) == 1
    task = queue["active"][0]
    assert task["total_articles"] == 3
    assert task["processed_articles"] == 0
    assert task["status"] == "pending"

    # 任务进入 recent 区域
    task_id = task["task_id"]
    db_task = db_session.get(CrawlTask, task_id)
    db_task.status = "completed"
    db_task.processed_articles = db_task.total_articles
    db_session.commit()
    spider_module.TASK_FAILURE_MESSAGES.pop(task_id, None)

    queue2 = queue_client.get("/crawl_queue").json()
    assert queue2["active"] == []
    assert any(t["task_id"] == task_id and t["status"] == "completed" for t in queue2["recent"])


def test_crawl_custom_url_accepts_multiple_urls(
    queue_client: TestClient, user_factory, db_session
):
    user_factory()
    _login(queue_client, "queue@example.com")
    assert db_session is not None

    resp = queue_client.post(
        "/crawl_custom_url",
        json={
            "source_url": "https://rsshub.rssforever.com/example/feed",
            "selected_urls": [
                "https://example.com/x",
                "https://example.com/y",
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    queue = queue_client.get("/crawl_queue").json()
    assert len(queue["active"]) == 1
    assert queue["active"][0]["total_articles"] == 2


def test_crawl_queue_failure_message_attached(
    queue_client: TestClient, user_factory, db_session
):
    user = user_factory()
    _login(queue_client, "queue@example.com")

    task = CrawlTask(
        user_id=user.id,
        status="failed",
        total_articles=2,
        processed_articles=0,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    spider_module.TASK_FAILURE_MESSAGES[task.id] = "RSSHub 请求失败（mock）"

    body = queue_client.get("/crawl_queue").json()
    recent = [t for t in body["recent"] if t["task_id"] == task.id]
    assert recent
    assert recent[0]["message"] == "RSSHub 请求失败（mock）"
