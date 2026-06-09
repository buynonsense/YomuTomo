# 新闻中心失败 Toast 细化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让新闻中心的失败 toast 明确告诉用户失败发生在哪一步，避免“失败了但不知道为什么”的情况。

**Architecture:** 后端仍然以 `CrawlTask.status` 作为任务总状态，但在任务结果里补充可读的失败原因，让前端可以直接展示更具体的文案。前端只做轻量映射：优先展示后端给出的明确错误信息，缺省时再回退到通用失败提示。

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, 原生 JavaScript, pytest, Docker Compose

---

### Task 1: 为新闻任务失败原因补测试

**Files:**
- Modify: `tests/test_api_coverage.py:585-660`

- [ ] **Step 1: Write the failing test**

```python
def test_crawl_and_save_articles_marks_failed_when_no_article_created(db_session, user_factory, monkeypatch: pytest.MonkeyPatch):
    user = user_factory(api_key="sk-test", base_url="https://example.com/v1", model="gpt-test")
    user_id = user.id
    task = CrawlTask(user_id=user.id, status="pending", total_articles=1, processed_articles=0)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    task_id = task.id

    from spider import rsshub_spider as spider_module

    monkeypatch.setattr(spider_module, "get_db", lambda: iter([db_session]))
    monkeypatch.setattr(
        spider_module,
        "get_feed_items",
        lambda limit=12: [{"title": "新闻", "url": "https://example.com/news/1", "source_url": "https://example.com/news/1"}],
    )
    monkeypatch.setattr(spider_module, "get_article_content", lambda url: None)
    monkeypatch.setattr(spider_module, "get_openai_client", lambda api_key, base_url: DummySyncClient())

    spider_module.crawl_and_save_articles_background(user.id, task.id, None)

    refreshed_task = db_session.get(CrawlTask, task_id)
    assert refreshed_task.status == "failed"
    assert refreshed_task.processed_articles == 0
    assert db_session.query(Article).filter(Article.user_id == user_id).count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_api_coverage.py::test_crawl_and_save_articles_marks_failed_when_no_article_created -v`
Expected: FAIL before implementation because the task still looks like a success path or the toast-facing state is still ambiguous.

- [ ] **Step 3: Keep the test focused on observable behavior**

If the test needs a helper, keep it in `tests/test_api_coverage.py` so it exercises the real background task through the same model and session that production uses.

### Task 2: 让后台任务返回明确失败原因

**Files:**
- Modify: `spider/rsshub_spider.py:338-478`

- [ ] **Step 1: Implement a small result helper inside the spider module**

```python
def _build_task_result(success: bool, message: str, task_id: int, processed_articles: int = 0) -> dict:
    return {
        "success": success,
        "message": message,
        "task_id": task_id,
        "processed_articles": processed_articles,
    }
```

- [ ] **Step 2: Return explicit failure messages for each known failure point**

```python
if not content:
    task.status = "failed"
    task.updated_at = utc_now()
    db.commit()
    return _build_task_result(False, "正文抓取失败：未能提取到新闻正文，请稍后重试。", task.id, processed_count)
```

```python
except AIClientError as e:
    log_with_time(f"⚠️ 处理文章时 AI 请求失败，已跳过该条: {news['title']}, 错误: {e}")
    continue
```

```python
task.status = "completed" if processed_count > 0 else "failed"
task.updated_at = utc_now()
db.commit()

if processed_count > 0:
    return _build_task_result(True, "新闻生成完成，可以前往“我的文章”查看。", task.id, processed_count)

return _build_task_result(False, "新闻生成失败：没有成功生成任何文章，请重试。", task.id, processed_count)
```

- [ ] **Step 3: Keep the old successful path intact**

Do not change the public `/crawl_news` response shape beyond adding `processed_articles` and more specific `message`. The route should still return a JSON object the current front end can read.

### Task 3: 让新闻中心 toast 直接展示明确原因

**Files:**
- Modify: `static/js/pages/news-center.js:85-250`

- [ ] **Step 1: Add a small helper that chooses the right toast copy**

```javascript
function getFailureToastMessage(data) {
  if (data && typeof data.message === 'string' && data.message.trim()) {
    return data.message.trim();
  }

  return '新闻生成失败，请稍后重试。';
}
```

- [ ] **Step 2: Use the helper in the completed/failed branch**

```javascript
if (data.status === 'failed') {
  notify(getFailureToastMessage(data), 'error');
  return;
}

if (data.status === 'completed') {
  if (getProcessedArticlesCount(data) <= 0) {
    if (taskId && !hasNotifiedTask(taskId)) {
      markTaskNotified(taskId);
      notify('新闻生成失败：没有成功生成任何文章，请重试。', 'error');
    }
    return;
  }

  if (taskId && !hasNotifiedTask(taskId)) {
    markTaskNotified(taskId);
    notify(getSuccessToastMessage(data), 'success');
    window.setTimeout(() => window.location.reload(), 1500);
  }
}
```

- [ ] **Step 3: Keep the success toast short and stable**

```javascript
function getSuccessToastMessage(data) {
  if (data && typeof data.message === 'string' && data.message.trim()) {
    return data.message.trim();
  }

  return '新闻生成完成，可以前往“我的文章”查看。';
}
```

### Task 4: 补全验证

**Files:**
- None

- [ ] **Step 1: Run the focused regression test**

Run: `pytest -q tests/test_api_coverage.py::test_crawl_and_save_articles_marks_failed_when_no_article_created -v`
Expected: PASS

- [ ] **Step 2: Run the full test suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 3: Rebuild and verify Docker**

Run: `docker compose up -d --build`

Then verify the service is reachable:

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
