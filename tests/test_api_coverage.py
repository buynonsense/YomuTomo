from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.model.models import Article, CrawlTask, Notification, User, VocabularyEntry
from app.routers import articles as articles_router
from app.services.services import hash_password as real_hash_password
from app.services.services import is_legacy_bcrypt_hash as real_is_legacy_bcrypt_hash
from app.services.services import verify_password as real_verify_password


class DummySyncClient:
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


class DummyAsyncClient:
    async def chat(self, messages, extra=None):
        return {"text": "ok"}


NEWS_FIXTURE_ITEMS = [
    {
        "title": "台風で強い雨　交通機関に影響",
        "title_with_ruby": "台風で<ruby>強<rt>つよ</rt></ruby>い雨　交通機関に影響",
        "outline": "台風の影響で各地で強い雨が降り、電車やバスに遅れが出ています。",
        "url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html",
        "source_url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html",
        "news_id": "ne2026010100001",
    },
    {
        "title": "新しい公園がオープンした",
        "title_with_ruby": "新しい<ruby>公園<rt>こうえん</rt></ruby>がオープンした",
        "outline": "地域の新しい公園が開園し、家族連れでにぎわっています。",
        "url": "https://www3.nhk.or.jp/news/easy/ne2026010100002/ne2026010100002.html",
        "source_url": "https://www3.nhk.or.jp/news/easy/ne2026010100002/ne2026010100002.html",
        "news_id": "ne2026010100002",
    },
    {
        "title": "駅で忘れ物を届ける仕組みを改善",
        "title_with_ruby": "駅で<ruby>忘<rt>わす</rt></ruby>れ<ruby>物<rt>もの</rt></ruby>を届ける仕組みを改善",
        "outline": "駅構内での忘れ物をより早く持ち主に返せるように仕組みが改善されました。",
        "url": "https://www3.nhk.or.jp/news/easy/ne2026010100003/ne2026010100003.html",
        "source_url": "https://www3.nhk.or.jp/news/easy/ne2026010100003/ne2026010100003.html",
        "news_id": "ne2026010100003",
    },
]


@pytest.fixture(autouse=True)
def _fast_passwords(monkeypatch: pytest.MonkeyPatch):
    from app.services import services as service_module

    monkeypatch.setattr(service_module, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setattr(service_module, "verify_password", lambda password, hashed: hashed == f"hashed:{password}")


@pytest.fixture()
def user_factory(db_session):
    def _make_user(
        email: str = "test@example.com",
        password_hash: str = "hashed:secret123",
        level: int = 1,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            level=level,
            openai_api_key=api_key,
            openai_base_url=base_url,
            openai_model=model,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make_user


@pytest.fixture()
def app_client(client: TestClient, db_session, monkeypatch: pytest.MonkeyPatch):
    from app import main as app_main
    from app.db import get_db
    from app.routers import auth, evaluation, pages
    from app.services.vocabulary import seed_vocabulary_entries as real_seed_vocabulary_entries
    from app.services import services as service_module
    import spider.nhk_spider as spider_module

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
    monkeypatch.setattr(articles_router, "get_openai_client", lambda api_key, base_url: DummySyncClient())
    monkeypatch.setattr(articles_router, "generate_ruby", lambda text, model, client: "<ruby>今天<rt>きょう</rt></ruby>")
    monkeypatch.setattr(articles_router, "extract_vocabulary", lambda text, model, client: [{"word": "天気", "meaning": "天气", "pronunciation": "てんき"}])
    monkeypatch.setattr(articles_router, "translate_to_chinese", lambda text, model, client: "今天天气很好")
    monkeypatch.setattr(articles_router, "generate_title", lambda text, model, client: "天气真好")
    monkeypatch.setattr(articles_router, "generate_emoji", lambda text, model, client: "🌤️")
    monkeypatch.setattr(
        articles_router,
        "generate_all_content",
        lambda text, model, client: (
            "<ruby>今天<rt>きょう</rt></ruby>",
            [{"word": "天气", "meaning": "天气", "pronunciation": "てんき"}],
            "今天天气很好",
            "天气真好",
            "🌤️",
        ),
    )
    monkeypatch.setattr(articles_router, "seed_vocabulary_entries", real_seed_vocabulary_entries)
    monkeypatch.setattr(
        articles_router,
        "attach_vocab_state",
        lambda db, user_id, vocab_items: [{**item, "mastered": item.get("word") == "天气"} for item in vocab_items],
    )
    monkeypatch.setattr(
        articles_router,
        "build_vocabulary_view_rows",
        lambda db, user_id, status=None: [
            {
                "id": 1,
                "word": "天气",
                "pronunciation": "てんき",
                "meaning": "天气",
                "status": "mastered",
                "article_id": 1,
                "article_title": "天气真好",
                "updated_at": None,
                "mastered_at": None,
            }
        ],
    )
    monkeypatch.setattr(
        articles_router,
        "toggle_vocabulary_status",
        lambda db, user_id, word, pronunciation=None, meaning=None, mastered=True, article_id=None: _toggle_vocab(
            db_session,
            user_id,
            word,
            pronunciation,
            meaning,
            mastered,
            article_id,
        ),
    )
    monkeypatch.setattr(articles_router.AIClient, "factory", staticmethod(lambda provider: DummyAsyncClient()))
    monkeypatch.setattr(
        articles_router,
        "get_openai_client",
        lambda api_key, base_url: DummySyncClient(),
    )
    monkeypatch.setattr(
        articles_router,
        "log_with_time",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        spider_module,
        "crawl_and_save_articles",
        lambda user_id, selected_urls=None: {
            "success": True,
            "message": "爬虫任务已启动，后台处理中",
            "task_id": 1,
            "selected_urls": selected_urls or [],
        },
    )
    monkeypatch.setattr(
        spider_module,
        "get_nhk_easy_news",
        lambda limit=12: NEWS_FIXTURE_ITEMS[:limit],
    )
    monkeypatch.setattr(service_module, "get_openai_client", lambda api_key, base_url: DummySyncClient())
    monkeypatch.setattr(service_module, "generate_ruby", lambda text, model, client: "<ruby>今天<rt>きょう</rt></ruby>")
    monkeypatch.setattr(service_module, "extract_vocabulary", lambda text, model, client: [{"word": "天气", "meaning": "天气", "pronunciation": "てんき"}])
    monkeypatch.setattr(service_module, "translate_to_chinese", lambda text, model, client: "今天天气很好")
    monkeypatch.setattr(service_module, "generate_title", lambda text, model, client: "天气真好")
    monkeypatch.setattr(service_module, "generate_emoji", lambda text, model, client: "🌤️")
    monkeypatch.setattr(
        service_module,
        "generate_all_content",
        lambda text, model, client: (
            "<ruby>今天<rt>きょう</rt></ruby>",
            [{"word": "天气", "meaning": "天气", "pronunciation": "てんき"}],
            "今天天气很好",
            "天气真好",
            "🌤️",
        ),
    )
    monkeypatch.setattr(evaluation, "normalize_to_hiragana", lambda text: text)
    app_main.app.dependency_overrides[get_db] = override_get_db
    yield client
    app_main.app.dependency_overrides.clear()


def _toggle_vocab(
    db_session,
    user_id: int,
    word: str,
    pronunciation: str | None = None,
    meaning: str | None = None,
    mastered: bool = True,
    article_id: int | None = None,
):
    entry = (
        db_session.query(VocabularyEntry)
        .filter(VocabularyEntry.user_id == user_id, VocabularyEntry.word == word)
        .first()
    )
    if entry is None:
        entry = VocabularyEntry(
            user_id=user_id,
            article_id=article_id,
            word=word,
            pronunciation=pronunciation,
            meaning=meaning,
            status="mastered" if mastered else "learning",
        )
        db_session.add(entry)
    else:
        entry.status = "mastered" if mastered else "learning"
    db_session.commit()
    db_session.refresh(entry)
    return entry


def _login(client: TestClient, email: str, password: str = "secret123"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def _create_article(db_session, user_id: int):
    article = Article(
        user_id=user_id,
        title="天气真好",
        emoji_cover="🌤️",
        original="今日は天気です",
        ruby_html="<ruby>今天<rt>きょう</rt></ruby>",
        translation="今天天气很好",
        vocab_json=json.dumps([{"word": "天气", "meaning": "天气", "pronunciation": "てんき"}], ensure_ascii=False),
        source_url="https://example.com/article",
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)
    return article


def test_health_endpoint(app_client: TestClient):
    response = app_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_shows_login_links_when_not_authenticated(app_client: TestClient):
    response = app_client.get("/")
    assert response.status_code == 200
    assert "登录" in response.text
    assert "注册" in response.text


def test_register_page_renders(app_client: TestClient):
    response = app_client.get("/register")
    assert response.status_code == 200
    assert "注册" in response.text


def test_register_rejects_mismatched_passwords(app_client: TestClient):
    response = app_client.post(
        "/register",
        data={"email": "user@example.com", "password": "secret123", "confirm_password": "secret456"},
    )
    assert response.status_code == 200
    assert "两次输入的密码不一致" in response.text


def test_register_creates_user_and_redirects(app_client: TestClient, db_session):
    response = app_client.post(
        "/register",
        data={"email": "user@example.com", "password": "secret123", "confirm_password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert db_session.execute(select(User).where(User.email == "user@example.com")).scalar_one().email == "user@example.com"


def test_register_accepts_long_passwords_with_real_hashing(client: TestClient, db_session, monkeypatch: pytest.MonkeyPatch):
    from app.routers import auth

    monkeypatch.setattr(auth, "hash_password", real_hash_password)
    monkeypatch.setattr(auth, "verify_password", real_verify_password)

    long_password = "a" * 80
    response = client.post(
        "/register",
        data={"email": "long@example.com", "password": long_password, "confirm_password": long_password},
        follow_redirects=False,
    )

    assert response.status_code == 303
    user = db_session.execute(select(User).where(User.email == "long@example.com")).scalar_one()
    assert user.password_hash.startswith("$pbkdf2-sha256$")
    assert auth.verify_password(long_password, user.password_hash) is True


def test_login_rejects_invalid_credentials(app_client: TestClient, user_factory):
    user_factory()
    response = app_client.post("/login", data={"email": "test@example.com", "password": "wrong"})
    assert response.status_code == 200
    assert "邮箱或密码错误" in response.text


def test_login_and_logout_flow(app_client: TestClient, user_factory):
    user = user_factory()
    login_response = _login(app_client, user.email)
    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/dashboard"

    logout_response = app_client.post("/logout", follow_redirects=False)
    assert logout_response.status_code == 303
    assert logout_response.headers["location"] == "/"


def test_login_upgrades_legacy_bcrypt_hash(client: TestClient, db_session, monkeypatch: pytest.MonkeyPatch):
    from app import main as app_main
    from app.db import get_db
    from app.routers import auth
    from app.services import services as service_module

    class FakeBcryptBackend:
        def checkpw(self, password: bytes, password_hash: bytes) -> bool:
            return password == b"secret123" and password_hash.startswith(b"$2b$")

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app_main.app.dependency_overrides[get_db] = override_get_db

    legacy_hash = "$2b$12$legacyhashlegacyhashlegacyhashlegacyhashlegacyhashleg"
    user = User(email="legacy@example.com", password_hash=legacy_hash)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    monkeypatch.setattr(service_module, "bcrypt_backend", FakeBcryptBackend())
    monkeypatch.setattr(auth, "hash_password", real_hash_password)
    monkeypatch.setattr(auth, "verify_password", real_verify_password)
    monkeypatch.setattr(auth, "is_legacy_bcrypt_hash", real_is_legacy_bcrypt_hash)

    response = client.post(
        "/login",
        data={"email": "legacy@example.com", "password": "secret123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    refreshed = db_session.get(User, user.id)
    assert refreshed.password_hash.startswith("$pbkdf2-sha256$")


def test_dashboard_redirects_when_not_logged_in(app_client: TestClient):
    response = app_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_renders_for_logged_in_user(app_client: TestClient, user_factory, db_session):
    user = user_factory()
    article = _create_article(db_session, user.id)
    _login(app_client, user.email)
    response = app_client.get("/dashboard")
    assert response.status_code == 200
    assert "我的文章" in response.text
    assert article.title in response.text


def test_loading_page_renders(app_client: TestClient):
    response = app_client.get("/loading")
    assert response.status_code == 200
    assert "AI处理中" in response.text


def test_reading_result_page_renders(app_client: TestClient):
    response = app_client.get("/reading_result")
    assert response.status_code == 200
    assert "处理结果" in response.text


def test_evaluate_endpoint_returns_score_json(app_client: TestClient):
    response = app_client.post("/evaluate", data={"original": "今日は天気です", "recognized": "今日は天気です"})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {
        "score",
        "similarity",
        "original_similarity",
        "kana_similarity",
        "original_html",
        "recognized_html",
        "matched_tokens",
        "miss_tokens",
        "extra_tokens",
        "original_tokens",
        "recognized_tokens",
    }
    assert data["score"] == 100
    assert data["matched_tokens"] >= 1
    assert data["original_tokens"] >= 1


def test_evaluate_endpoint_marks_mismatched_tokens(app_client: TestClient):
    response = app_client.post("/evaluate", data={"original": "今日は天気です", "recognized": "今日は雨です"})
    assert response.status_code == 200
    data = response.json()
    assert data["miss_tokens"] >= 1
    assert data["extra_tokens"] >= 1
    assert 'evaluation-token--miss' in data["original_html"]
    assert 'evaluation-token--extra' in data["recognized_html"]


def test_process_text_async_requires_login(app_client: TestClient):
    response = app_client.post("/process_text_async", data={"text": "今日は天気です"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_process_text_async_creates_article_and_vocab(app_client: TestClient, user_factory, db_session):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    _login(app_client, user.email)
    response = app_client.post("/process_text_async", data={"text": "今日は天気です"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["redirect_url"].startswith("/articles/")
    article = db_session.query(Article).filter(Article.user_id == user.id).one()
    assert article.title == "天气真好"
    vocab_entry = db_session.query(VocabularyEntry).filter(VocabularyEntry.user_id == user.id).one()
    assert vocab_entry.word == "天气"


def test_view_article_requires_login(app_client: TestClient, user_factory, db_session):
    user = user_factory()
    article = _create_article(db_session, user.id)
    response = app_client.get(f"/articles/{article.id}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_view_article_renders_logged_in_user(app_client: TestClient, user_factory, db_session):
    user = user_factory()
    article = _create_article(db_session, user.id)
    _login(app_client, user.email)
    response = app_client.get(f"/articles/{article.id}")
    assert response.status_code == 200
    assert "今天天气很好" in response.text
    assert "天气" in response.text


def test_vocabulary_requires_login(app_client: TestClient):
    response = app_client.get("/vocabulary", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_vocabulary_renders_rows(app_client: TestClient, user_factory, db_session):
    user = user_factory()
    article = _create_article(db_session, user.id)
    db_session.add(
        VocabularyEntry(
            user_id=user.id,
            article_id=article.id,
            word="天气",
            pronunciation="てんき",
            meaning="天气",
            status="mastered",
        )
    )
    db_session.commit()
    _login(app_client, user.email)
    response = app_client.get("/vocabulary")
    assert response.status_code == 200
    assert "我的生词本" in response.text
    assert "天气" in response.text


def test_toggle_vocabulary_creates_entry(app_client: TestClient, user_factory):
    user = user_factory()
    _login(app_client, user.email)
    response = app_client.post(
        "/vocabulary/toggle",
        json={"word": "天气", "pronunciation": "てんき", "meaning": "天气", "mastered": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["mastered"] is True


def test_get_ai_config_reports_login_state(app_client: TestClient):
    response = app_client.get("/get_ai_config")
    assert response.status_code == 200
    assert response.json() == {"error": "未登录"}


def test_save_ai_config_updates_user(app_client: TestClient, user_factory, db_session):
    user = user_factory()
    _login(app_client, user.email)
    response = app_client.post(
        "/save_ai_config",
        data={
            "openai_api_key": "sk-test",
            "openai_base_url": "https://example.com/v1",
            "openai_model": "gpt-test",
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    refreshed = db_session.get(User, user.id)
    assert refreshed.openai_api_key == "sk-test"
    assert refreshed.openai_model == "gpt-test"


def test_save_ai_config_creates_notification_with_internal_source_url(app_client: TestClient, user_factory, db_session):
    user = user_factory()
    _login(app_client, user.email)

    response = app_client.post(
        "/save_ai_config",
        data={
            "openai_api_key": "sk-test",
            "openai_base_url": "https://example.com/v1",
            "openai_model": "gpt-test",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    notifications = db_session.query(Notification).filter(Notification.user_id == user.id).all()
    assert len(notifications) == 1
    assert notifications[0].type == "settings_saved"
    assert notifications[0].source_url.startswith("/")
    assert "open_settings=ai" in notifications[0].source_url


def test_get_user_level_requires_login(app_client: TestClient):
    response = app_client.get("/get_user_level")
    assert response.status_code == 200
    assert response.json() == {"error": "未登录"}


def test_update_user_level_validates_and_persists(app_client: TestClient, user_factory, db_session):
    user = user_factory()
    _login(app_client, user.email)
    response = app_client.post("/update_user_level", json={"level": 4})
    assert response.status_code == 200
    assert response.json() == {"message": "等级更新成功"}
    assert db_session.get(User, user.id).level == 4


def test_crawl_status_and_crawl_news_flow(app_client: TestClient, user_factory, db_session):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    _login(app_client, user.email)
    db_session.add(CrawlTask(user_id=user.id, status="completed", total_articles=1, processed_articles=1))
    db_session.commit()

    status_response = app_client.get("/crawl_status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"

    response = app_client.post("/crawl_news")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_notification_model_persists_and_marks_read(db_session, user_factory):
    user = user_factory()
    notification = Notification(
        user_id=user.id,
        type="news_failed",
        title="新闻生成失败",
        message="正文抓取失败：未能提取到新闻正文，请稍后重试。",
        source_task_id=12,
        source_url="/news_center",
        is_read=False,
    )

    db_session.add(notification)
    db_session.commit()
    db_session.refresh(notification)

    assert notification.id is not None
    assert notification.is_read is False
    assert notification.read_at is None


def test_notifications_api_lists_unread_and_marks_all_read(app_client: TestClient, user_factory, db_session):
    user = user_factory()
    user_id = user.id
    _login(app_client, user.email)

    db_session.add(
        Notification(
            user_id=user_id,
            type="news_success",
            title="新闻生成完成",
            message="新闻生成完成，可以前往“我的文章”查看。",
            source_task_id=22,
            source_url="/dashboard",
            is_read=False,
        )
    )
    db_session.commit()

    list_response = app_client.get("/notifications")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["unread_count"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["title"] == "新闻生成完成"

    unread_response = app_client.get("/notifications/unread-count")
    assert unread_response.status_code == 200
    assert unread_response.json()["unread_count"] == 1

    mark_response = app_client.post("/notifications/mark-read", json={"all": True})
    assert mark_response.status_code == 200
    assert mark_response.json()["success"] is True
    assert mark_response.json()["affected"] == 1

    refreshed = app_client.get("/notifications/unread-count")
    assert refreshed.status_code == 200
    assert refreshed.json()["unread_count"] == 0


def test_notifications_api_lists_without_login(app_client: TestClient):
    response = app_client.get("/notifications")
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["message"] == "未登录"


def test_notifications_api_marks_single_notification_read(app_client: TestClient, user_factory, db_session):
    user = user_factory()
    user_id = user.id
    _login(app_client, user.email)

    notification = Notification(
        user_id=user_id,
        type="system_error",
        title="系统报错",
        message="系统报错：数据库连接失败。",
        source_task_id=None,
        source_url="/",
        is_read=False,
    )
    db_session.add(notification)
    db_session.commit()
    db_session.refresh(notification)

    mark_response = app_client.post("/notifications/mark-read", json={"notification_id": notification.id})
    assert mark_response.status_code == 200
    assert mark_response.json()["success"] is True
    assert mark_response.json()["affected"] == 1

    refreshed = db_session.get(Notification, notification.id)
    assert refreshed is not None
    assert refreshed.is_read is True
    assert refreshed.read_at is not None


def test_notifications_api_deletes_single_and_all_notifications(app_client: TestClient, user_factory, db_session):
    user = user_factory()
    _login(app_client, user.email)

    first = Notification(
        user_id=user.id,
        type="system_error",
        title="系统报错",
        message="系统报错：数据库连接失败。",
        source_task_id=None,
        source_url="/",
        is_read=False,
    )
    second = Notification(
        user_id=user.id,
        type="news_success",
        title="新闻生成完成",
        message="新闻生成完成，可以前往“我的文章”查看。",
        source_task_id=99,
        source_url="/dashboard",
        is_read=False,
    )
    db_session.add_all([first, second])
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(second)
    first_id = first.id
    second_id = second.id

    delete_one_response = app_client.post("/notifications/delete", json={"notification_id": first_id})
    assert delete_one_response.status_code == 200
    assert delete_one_response.json()["success"] is True
    assert delete_one_response.json()["affected"] == 1
    assert db_session.get(Notification, first_id) is None
    assert db_session.get(Notification, second_id) is not None

    delete_all_response = app_client.post("/notifications/delete", json={"all": True})
    assert delete_all_response.status_code == 200
    assert delete_all_response.json()["success"] is True
    assert delete_all_response.json()["affected"] == 1
    assert db_session.get(Notification, second_id) is None


def test_article_view_exposes_highlight_context(app_client: TestClient, user_factory, db_session):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    article = _create_article(db_session, user.id)
    _login(app_client, user.email)

    response = app_client.get(f"/articles/{article.id}?highlight_notification=123&highlight_article={article.id}")

    assert response.status_code == 200
    assert str(article.id) in response.text


def test_crawl_and_save_articles_writes_failure_notification_and_is_idempotent(
    db_session,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    user_id = user.id
    task = CrawlTask(user_id=user.id, status="pending", total_articles=1, processed_articles=0)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    from spider import nhk_spider as spider_module

    monkeypatch.setattr(spider_module, "get_db", lambda: iter([db_session]))
    monkeypatch.setattr(
        spider_module,
        "get_nhk_easy_news",
        lambda limit=12: [
            {
                "title": "新闻",
                "url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html",
                "source_url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html",
            }
        ],
    )
    monkeypatch.setattr(spider_module, "get_article_content", lambda url: None)
    monkeypatch.setattr(spider_module, "get_openai_client", lambda api_key, base_url: DummySyncClient())

    result = spider_module.crawl_and_save_articles_background(user_id, task.id, None)
    repeat_result = spider_module.crawl_and_save_articles_background(user_id, task.id, None)

    notifications = db_session.query(Notification).filter(Notification.user_id == user_id).all()

    assert result["success"] is False
    assert result["message"] == "正文抓取失败：未能提取到新闻正文，请稍后重试。"
    assert repeat_result["success"] is False
    assert len(notifications) == 1
    assert notifications[0].type == "news_failed"
    assert notifications[0].source_task_id == task.id


def test_crawl_and_save_articles_writes_success_notification(
    db_session,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    user_id = user.id
    task = CrawlTask(user_id=user.id, status="pending", total_articles=1, processed_articles=0)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    from spider import nhk_spider as spider_module

    monkeypatch.setattr(spider_module, "get_db", lambda: iter([db_session]))
    monkeypatch.setattr(
        spider_module,
        "get_nhk_easy_news",
        lambda limit=12: [
            {
                "title": "新闻",
                "url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html",
                "source_url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html",
            }
        ],
    )
    monkeypatch.setattr(spider_module, "get_article_content", lambda url: "这是正文内容，可以继续处理")
    monkeypatch.setattr(spider_module, "get_openai_client", lambda api_key, base_url: DummySyncClient())

    result = spider_module.crawl_and_save_articles_background(user_id, task.id, None)
    repeat_result = spider_module.crawl_and_save_articles_background(user_id, task.id, None)

    notifications = db_session.query(Notification).filter(Notification.user_id == user_id).all()

    assert result["success"] is True
    assert result["message"] == "新闻生成完成，可以前往“我的文章”查看。"
    assert repeat_result["success"] is True
    assert len(notifications) == 1
    assert notifications[0].type == "news_success"
    assert notifications[0].source_task_id == task.id


def test_news_center_renders_multiple_items(app_client: TestClient, user_factory):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    _login(app_client, user.email)

    response = app_client.get("/news_center?limit=2")

    assert response.status_code == 200
    assert "NHK 新闻中心" in response.text
    assert NEWS_FIXTURE_ITEMS[0]["title"] in response.text
    assert NEWS_FIXTURE_ITEMS[1]["title"] in response.text
    assert NEWS_FIXTURE_ITEMS[2]["title"] not in response.text


def test_crawl_news_accepts_selected_news_url(app_client: TestClient, user_factory, monkeypatch: pytest.MonkeyPatch):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    _login(app_client, user.email)

    captured = {}

    def fake_crawl(user_id, selected_urls=None):
        captured["user_id"] = user_id
        captured["selected_urls"] = list(selected_urls or [])
        return {"success": True, "message": "爬虫任务已启动，后台处理中", "task_id": 99}

    from spider import nhk_spider as spider_module

    monkeypatch.setattr(spider_module, "crawl_and_save_articles", fake_crawl)

    response = app_client.post("/crawl_news", json={"news_url": NEWS_FIXTURE_ITEMS[1]["source_url"]})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured["user_id"] == user.id
    assert captured["selected_urls"] == [NEWS_FIXTURE_ITEMS[1]["source_url"]]


def test_crawl_and_save_articles_marks_failed_when_no_article_created(db_session, user_factory, monkeypatch: pytest.MonkeyPatch):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    user_id = user.id
    user_email = user.email
    task = CrawlTask(user_id=user.id, status="pending", total_articles=1, processed_articles=0)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    task_id = task.id
    task_id = task.id

    from spider import nhk_spider as spider_module

    monkeypatch.setattr(spider_module, "get_db", lambda: iter([db_session]))
    monkeypatch.setattr(
        spider_module,
        "get_nhk_easy_news",
        lambda limit=12: [{"title": "新闻", "url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html", "source_url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html"}],
    )
    monkeypatch.setattr(spider_module, "get_article_content", lambda url: None)
    monkeypatch.setattr(spider_module, "get_openai_client", lambda api_key, base_url: DummySyncClient())

    spider_module.crawl_and_save_articles_background(user.id, task.id, None)

    refreshed_task = db_session.get(CrawlTask, task_id)
    assert refreshed_task.status == "failed"
    assert refreshed_task.processed_articles == 0
    assert db_session.query(Article).filter(Article.user_id == user_id).count() == 0


def test_crawl_and_save_articles_background_returns_clear_failure_message_when_body_fetch_fails(
    app_client: TestClient,
    db_session,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
): 
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    user_id = user.id
    user_email = user.email
    task = CrawlTask(user_id=user.id, status="pending", total_articles=1, processed_articles=0)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    task_id = task.id

    from spider import nhk_spider as spider_module

    monkeypatch.setattr(spider_module, "get_db", lambda: iter([db_session]))
    monkeypatch.setattr(
        spider_module,
        "get_nhk_easy_news",
        lambda limit=12: [
            {
                "title": "新闻",
                "url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html",
                "source_url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html",
            }
        ],
    )
    monkeypatch.setattr(spider_module, "get_article_content", lambda url: None)
    monkeypatch.setattr(spider_module, "get_openai_client", lambda api_key, base_url: DummySyncClient())

    result = spider_module.crawl_and_save_articles_background(user.id, task_id, None)

    _login(app_client, user_email)
    status_response = app_client.get("/crawl_status")

    refreshed_task = db_session.get(CrawlTask, task_id)
    assert result["success"] is False
    assert result["message"] == "正文抓取失败：未能提取到新闻正文，请稍后重试。"
    assert status_response.status_code == 200
    assert status_response.json()["message"] == "正文抓取失败：未能提取到新闻正文，请稍后重试。"
    assert refreshed_task.status == "failed"
    assert refreshed_task.processed_articles == 0
    assert db_session.query(Article).filter(Article.user_id == user_id).count() == 0


def test_crawl_and_save_articles_background_returns_generic_failure_message_when_no_article_is_generated(
    db_session,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    user_id = user.id
    task = CrawlTask(user_id=user.id, status="pending", total_articles=1, processed_articles=0)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    task_id = task.id

    from spider import nhk_spider as spider_module

    monkeypatch.setattr(spider_module, "get_db", lambda: iter([db_session]))
    monkeypatch.setattr(
        spider_module,
        "get_nhk_easy_news",
        lambda limit=12: [
            {
                "title": "新闻",
                "url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html",
                "source_url": "https://www3.nhk.or.jp/news/easy/ne2026010100001/ne2026010100001.html",
            }
        ],
    )
    monkeypatch.setattr(spider_module, "get_article_content", lambda url: "这是正文内容，可以继续处理")
    monkeypatch.setattr(spider_module, "generate_all_content", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("生成失败")))
    monkeypatch.setattr(spider_module, "get_openai_client", lambda api_key, base_url: DummySyncClient())

    result = spider_module.crawl_and_save_articles_background(user.id, task_id, None)

    refreshed_task = db_session.get(CrawlTask, task_id)
    assert result["success"] is False
    assert result["message"] == "新闻生成失败：没有成功生成任何文章，请重试。"
    assert refreshed_task.status == "failed"
    assert refreshed_task.processed_articles == 0
    assert db_session.query(Article).filter(Article.user_id == user_id).count() == 0


def test_crawl_custom_url_starts_background_task(app_client: TestClient, user_factory, monkeypatch: pytest.MonkeyPatch):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    _login(app_client, user.email)

    captured = {}

    def fake_crawl(user_id, url):
        captured["user_id"] = user_id
        captured["url"] = url
        return {"success": True, "message": "自定义 URL 已启动，后台处理中", "task_id": 101, "selected_urls": [url]}

    from spider import nhk_spider as spider_module

    monkeypatch.setattr(spider_module, "crawl_custom_url", fake_crawl)

    response = app_client.post("/crawl_custom_url", json={"url": "https://example.com/jp-article"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["task_id"] == 101
    assert captured["user_id"] == user.id
    assert captured["url"] == "https://example.com/jp-article"


def test_crawl_custom_url_rejects_invalid_scheme(app_client: TestClient, user_factory):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    _login(app_client, user.email)

    response = app_client.post("/crawl_custom_url", json={"url": "javascript:alert(1)"})

    assert response.status_code == 200
    assert response.json()["success"] is False


def test_auth_and_article_routes_have_template_coverage(app_client: TestClient):
    assert app_client.get("/login").status_code == 200
    assert app_client.get("/register").status_code == 200
    assert app_client.get("/loading").status_code == 200
