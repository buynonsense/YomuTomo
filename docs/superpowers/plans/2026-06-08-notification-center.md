# 通知中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 YomuTomo 增加一个全站统一通知中心，通知落库并按用户跨设备同步，导航栏提供未读角标和历史通知面板，打开后自动清空未读数。

**Architecture:** 新增独立 `Notification` 数据模型和通知服务，负责写入、查询、未读统计与已读标记。后端先把现有新闻任务接入通知写入，再通过轻量 API 暴露通知列表和未读数；前端在全局导航中增加铃铛按钮与下拉面板，打开面板时批量标记已读并刷新角标。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Jinja2, 原生 JavaScript, pytest, Docker Compose

---

### Task 1: 新增通知数据模型与迁移

**Files:**
- Modify: `app/model/models.py:1-75`
- Create: `alembic/versions/<new_revision>_add_notifications_table.py`
- Test: `tests/test_api_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
def test_notification_model_persists_and_marks_read(db_session, user_factory):
    from app.model.models import Notification

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_api_coverage.py::test_notification_model_persists_and_marks_read -v`
Expected: FAIL before the model and migration exist.

- [ ] **Step 3: Write minimal implementation**

```python
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    source_task_id = Column(Integer, nullable=True, index=True)
    source_url = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, nullable=False)

    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "type", "source_task_id", name="uq_notifications_user_type_task"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_api_coverage.py::test_notification_model_persists_and_marks_read -v`
Expected: PASS after the model is added and metadata creates the table.

- [ ] **Step 5: Create and apply Alembic migration**

Use the existing Alembic pattern in `alembic/versions/` to create the `notifications` table with the columns and unique constraint above.

### Task 2: 新增通知服务和 API

**Files:**
- Create: `app/services/notifications.py`
- Modify: `app/routers/context.py` if needed for current-user access consistency
- Modify: `app/routers/articles.py:1-589`
- Test: `tests/test_api_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
def test_notifications_api_lists_and_marks_read(app_client, user_factory, db_session):
    from app.model.models import Notification

    user = user_factory()
    _login(app_client, user.email)
    db_session.add(
        Notification(
            user_id=user.id,
            type="news_failed",
            title="新闻生成失败",
            message="正文抓取失败：未能提取到新闻正文，请稍后重试。",
            source_task_id=12,
            source_url="/news_center",
            is_read=False,
        )
    )
    db_session.commit()

    list_response = app_client.get("/notifications")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["unread_count"] == 1
    assert len(payload["items"]) == 1

    mark_response = app_client.post("/notifications/mark-read", json={"all": True})
    assert mark_response.status_code == 200
    assert mark_response.json()["success"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_api_coverage.py::test_notifications_api_lists_and_marks_read -v`
Expected: FAIL before the API exists.

- [ ] **Step 3: Write minimal implementation**

```python
def list_notifications(db: Session, user_id: int) -> tuple[list[dict], int]:
    # 按时间倒序返回当前用户通知和未读数
    ...

def mark_notifications_read(db: Session, user_id: int, notification_id: int | None = None) -> int:
    # 标记当前用户全部或单条通知为已读，并返回受影响数量
    ...
```

```python
@router.get("/notifications")
async def get_notifications(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"error": "未登录"}
    items, unread_count = list_notifications(db, user.id)
    return {"items": items, "unread_count": unread_count}
```

```python
@router.post("/notifications/mark-read")
async def mark_notifications_read_endpoint(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"success": False, "message": "未登录"}
    data = await request.json()
    notification_id = data.get("notification_id") if isinstance(data, dict) else None
    affected = mark_notifications_read(db, user.id, notification_id)
    return {"success": True, "affected": affected}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_api_coverage.py::test_notifications_api_lists_and_marks_read -v`
Expected: PASS after the endpoints and service are added.

### Task 3: 让新闻任务写入通知

**Files:**
- Modify: `spider/rsshub_spider.py:1-478`
- Modify: `app/routers/articles.py:370-430` if the route needs to capture and persist notification payloads
- Test: `tests/test_api_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
def test_news_crawl_creates_notification_for_failure(app_client, user_factory, monkeypatch):
    # 让新闻任务走失败路径，然后断言 notifications 表里生成了一条失败通知
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_api_coverage.py::test_news_crawl_creates_notification_for_failure -v`
Expected: FAIL before write-notification logic exists.

- [ ] **Step 3: Write minimal implementation**

```python
def create_notification(db: Session, *, user_id: int, type: str, title: str, message: str, source_task_id: int | None = None, source_url: str | None = None) -> Notification:
    # 使用 user_id + type + source_task_id 做幂等写入
    ...
```

```python
create_notification(
    db,
    user_id=user_id,
    type="news_failed",
    title="新闻生成失败",
    message="正文抓取失败：未能提取到新闻正文，请稍后重试。",
    source_task_id=task.id,
    source_url="/news_center",
)
```

```python
create_notification(
    db,
    user_id=user_id,
    type="news_success",
    title="新闻生成完成",
    message="新闻生成完成，可以前往“我的文章”查看。",
    source_task_id=task.id,
    source_url="/dashboard",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_api_coverage.py::test_news_crawl_creates_notification_for_failure -v`
Expected: PASS after新闻任务写通知成功。

### Task 4: 在导航栏加入通知铃铛和角标

**Files:**
- Modify: `templates/partials/global_nav.html:1-27`
- Modify: `static/css/components/common.css:3-329`

- [ ] **Step 1: Write the failing test**

```python
def test_global_nav_renders_notification_button_in_logged_in_state(client):
    response = client.get("/news_center")
    assert "通知" in response.text or "bell" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_pages_templates.py -q`
Expected: FAIL before the nav button is added.

- [ ] **Step 3: Write minimal implementation**

```html
<button id="global-notifications-btn" type="button" class="global-nav__icon-btn" aria-label="通知">
  🔔
  <span id="global-notifications-badge" class="global-nav__badge" hidden>0</span>
</button>
```

```css
.global-nav__icon-btn {
  position: relative;
  ...
}

.global-nav__badge {
  position: absolute;
  top: -6px;
  right: -6px;
  ...
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_pages_templates.py -q`
Expected: PASS once the button is rendered in the navigation.

### Task 5: 实现通知面板前端加载、已读和角标清空

**Files:**
- Create: `templates/partials/global_notifications_panel.html`
- Create: `static/js/modules/notifications.js`
- Modify: `templates/partials/global_nav.html:1-27`
- Modify: `static/js/common.js` only if the existing toast utility needs integration hooks

- [ ] **Step 1: Write the failing test**

```python
def test_notifications_panel_template_exists():
    from pathlib import Path
    assert Path("templates/partials/global_notifications_panel.html").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_pages_templates.py -q`
Expected: FAIL before the partial exists.

- [ ] **Step 3: Write minimal implementation**

```javascript
async function loadNotifications() {
  const response = await fetch('/notifications');
  const data = await response.json();
  renderNotifications(data.items || []);
  updateBadge(data.unread_count || 0);
}

async function markAllRead() {
  await fetch('/notifications/mark-read', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ all: true }),
  });
  updateBadge(0);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_pages_templates.py -q`
Expected: PASS after panel template and JS are added.

### Task 6: 补全验证与 Docker 检查

**Files:**
- None

- [ ] **Step 1: Run full tests**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 2: Rebuild and verify Docker**

Run: `docker compose up -d --build`

Then verify service access:

```bash
python - <<'PY'
import time
import urllib.request

for _ in range(20):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/news_center', timeout=10) as resp:
            print(resp.status)
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit('service not reachable')
PY
```

Expected: `200`
