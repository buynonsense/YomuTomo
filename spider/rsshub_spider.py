from __future__ import annotations

import json
import threading
from typing import Iterable

from app.core.config import settings
from app.db import get_db
from app.model.models import Article, CrawlTask, User
from app.services.ai_client_async import AIClientError
from app.services.notifications import create_notification
from app.services import rsshub_feed as rsshub_feed_module
from app.services.rsshub_feed import RSSHubFetchError, fetch_rsshub_feed_items, first_item_content, normalize_rsshub_source_url
from app.services.services import generate_all_content, get_openai_client, log_with_time
from app.utils.time import utc_now

DEFAULT_NEWS_SOURCE_URL = settings.NEWS_CENTER_SOURCE_URL
TASK_FAILURE_MESSAGES: dict[int, str] = {}
requests = rsshub_feed_module.requests
_ORIGINAL_GET_FEED_ITEMS = None


def _normalize_selected_urls(selected_urls: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    for url in selected_urls or []:
        if not isinstance(url, str):
            continue
        value = url.strip()
        if not value:
            continue
        if value.startswith(("http://", "https://", "rsshub://")):
            normalized.append(value)
    return normalized


def _item_content(item: dict) -> str:
    for key in ("content", "outline", "title"):
        value = item.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _item_url(item: dict) -> str | None:
    for key in ("url", "source_url"):
        value = item.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _build_crawl_result(success: bool, message: str, task_id: int, processed_articles: int) -> dict[str, object]:
    TASK_FAILURE_MESSAGES[task_id] = message
    return {
        "success": success,
        "message": message,
        "task_id": task_id,
        "processed_articles": processed_articles,
    }


def fetch_feed_items(source_url: str | None = None, limit: int = 12) -> list[dict]:
    source = source_url or DEFAULT_NEWS_SOURCE_URL
    current_get_feed_items = globals().get("get_feed_items")
    if _ORIGINAL_GET_FEED_ITEMS is not None and current_get_feed_items is not _ORIGINAL_GET_FEED_ITEMS:
        try:
            return current_get_feed_items(source_url=source_url, limit=limit)
        except TypeError:
            return current_get_feed_items(source, limit=limit)

    return fetch_rsshub_feed_items(source, limit=limit)


def get_feed_items(source_url: str | None = None, limit: int = 12) -> list[dict]:
    source = source_url or DEFAULT_NEWS_SOURCE_URL
    try:
        return fetch_feed_items(source, limit=limit)
    except RSSHubFetchError as e:
        log_with_time(f"获取 RSSHub 订阅源失败 source_url={source}: {e}")
        return []
    except Exception as e:
        log_with_time(f"获取 RSSHub 订阅源失败 source_url={source}: {e}")
        return []


def get_news_items(source_url: str | None = None, limit: int = 12) -> list[dict]:
    return get_feed_items(source_url, limit=limit)


_ORIGINAL_GET_FEED_ITEMS = get_feed_items


def resolve_feed_items(
    source_url: str | None = None,
    selected_urls: Iterable[str] | None = None,
    limit: int = 12,
) -> list[dict]:
    """按 URL 过滤指定订阅源里的条目。"""
    normalized_urls = _normalize_selected_urls(selected_urls)
    feed_limit = max(limit, len(normalized_urls), 12)
    feed_items = fetch_feed_items(source_url, limit=feed_limit)

    if not normalized_urls:
        return feed_items

    selected: list[dict] = []
    news_map: dict[str, dict] = {}
    for item in feed_items:
        for key in (item.get("url"), item.get("source_url")):
            if isinstance(key, str) and key not in news_map:
                news_map[key] = item

    for url in normalized_urls:
        item = news_map.get(url)
        if item and item not in selected:
            selected.append(item)

    return selected


def get_article_content(url: str | None) -> str | None:
    """从 RSSHub 源里解析内容，保留一个兼容入口给旧调用点。"""
    normalized_source = normalize_rsshub_source_url(url)
    if normalized_source:
        return first_item_content(normalized_source)

    if not isinstance(url, str) or not url.strip():
        return None

    for item in get_feed_items(limit=20):
        if url == item.get("url") or url == item.get("source_url"):
            content = _item_content(item)
            if content:
                return content

    return None


def _format_rsshub_failure_message(exc: Exception, default_message: str) -> str:
    if isinstance(exc, RSSHubFetchError):
        return str(exc)

    return default_message


def generate_simplified_article(original_text, user_level, model, client):
    levels = {
        1: "JLPT N5水平（基础词汇和语法）",
        2: "JLPT N4水平（日常会话）",
        3: "JLPT N3水平（一般性话题）",
        4: "JLPT N2水平（抽象话题）",
        5: "JLPT N1水平（复杂话题）",
    }
    level_desc = levels.get(user_level, "JLPT N3水平（一般性话题）")
    prompt = f"请将以下日文文章简化到适合{level_desc}的学习者阅读水平。保持主要内容，但使用相应等级的词汇和句子结构，只输出结果，不要说无关的话。\n\n原文：{original_text}"
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except AIClientError as e:
        log_with_time(f"[AI] generate_simplified_article failed, fallback to original: {e}")
        return original_text
    except Exception as e:
        log_with_time(f"[AI] generate_simplified_article unexpected error, fallback to original: {e}")
        return original_text


def _generate_article_from_item(user_id: int, user: User, item: dict, client) -> Article | None:
    content = _item_content(item)
    if not content:
        return None

    simplified = generate_simplified_article(content, user.level, user.openai_model, client)
    ruby_text, vocab, translation, title, emoji = generate_all_content(simplified, user.openai_model, client)
    source_url = _item_url(item)
    if not source_url:
        return None

    return Article(
        user_id=user_id,
        title=title,
        emoji_cover=emoji,
        original=content,
        ruby_html=ruby_text,
        translation=translation,
        vocab_json=json.dumps(vocab, ensure_ascii=False),
        source_url=source_url,
    )


def _save_articles_from_items(
    db,
    user_id: int,
    user: User,
    task: CrawlTask,
    items: list[dict],
    success_message: str,
    failure_message: str,
) -> dict[str, object]:
    if not items:
        task.status = "failed"
        task.updated_at = utc_now()
        db.commit()
        try:
            create_notification(
                db,
                user_id=user_id,
                type="news_failed",
                title="新闻生成失败",
                message=failure_message,
                source_task_id=task.id,
                source_url="/news_center",
            )
        except Exception as e:
            log_with_time(f"❌ 写入新闻失败通知失败 task_id={task.id}: {e}", level="ERROR")
        return _build_crawl_result(False, failure_message, task.id, 0)

    task.total_articles = len(items)
    db.commit()

    client = get_openai_client(user.openai_api_key, user.openai_base_url)
    processed_count = 0
    last_ai_error: str | None = None  # 记录最后一次 AI 报错, 用于 failure 通知

    for item in items:
        try:
            article = _generate_article_from_item(user_id, user, item, client)
            if not article:
                log_with_time(f"⚠️ 条目缺少可用正文，跳过: {item.get('title')}")
                continue

            db.add(article)
            processed_count += 1
            task.processed_articles = processed_count
            task.updated_at = utc_now()
            db.commit()
            log_with_time(f"✅ 已处理 {processed_count}/{task.total_articles} 篇文章: {item.get('title')}")
        except AIClientError as e:
            # generate_all_content 内部已经把 AIClientError 转成可读中文 (例如
            # "AI 接口超时..." / "AI 接口鉴权失败 (HTTP 401)..."), 直接透传
            err_text = str(e)
            last_ai_error = err_text
            log_with_time(f"⚠️ 处理文章时 AI 请求失败，已跳过该条: {item.get('title')}, 错误: {err_text}")
            continue
        except Exception as e:
            err_text = f"AI 生成失败: {e}"
            last_ai_error = err_text
            log_with_time(f"❌ 处理文章失败: {item.get('title')}, 错误: {e}")
            import traceback

            traceback.print_exc()
            continue

    task.status = "completed" if processed_count > 0 else "failed"
    task.updated_at = utc_now()
    db.commit()

    if processed_count > 0:
        try:
            create_notification(
                db,
                user_id=user_id,
                type="news_success",
                title="新闻生成完成",
                message=success_message,
                source_task_id=task.id,
                source_url="/dashboard",
            )
        except Exception as e:
            log_with_time(f"❌ 写入新闻成功通知失败 task_id={task.id}: {e}", level="ERROR")
        return _build_crawl_result(True, success_message, task.id, processed_count)

    # 全部失败: 如果是因为 AI 报错, 用真实原因替换通用提示
    final_failure_message = last_ai_error or failure_message
    try:
        create_notification(
            db,
            user_id=user_id,
            type="news_failed",
            title="新闻生成失败",
            message=final_failure_message,
            source_task_id=task.id,
            source_url="/news_center",
        )
    except Exception as e:
        log_with_time(f"❌ 写入新闻失败通知失败 task_id={task.id}: {e}", level="ERROR")
    return _build_crawl_result(False, final_failure_message, task.id, processed_count)


def get_houkago_news():
    """获取放課後NEWS - 暂时保留空实现。"""
    try:
        log_with_time("放課後NEWS网站不可访问，跳过此部分")
        return []
    except Exception as e:
        log_with_time(f"获取放課後NEWS失败: {e}")
        return []


def _crawl_feed_background(
    user_id: int,
    task_id: int,
    source_url: str | None,
    selected_urls: Iterable[str] | None = None,
) -> dict[str, object] | None:
    db = next(get_db())
    selected_url_list = _normalize_selected_urls(selected_urls)
    task = None
    normalized_source = source_url or DEFAULT_NEWS_SOURCE_URL

    try:
        task = db.query(CrawlTask).filter(CrawlTask.id == task_id).first()
        if not task:
            return _build_crawl_result(False, "新闻生成失败：任务不存在。", task_id, 0)

        if task.status in {"completed", "failed"}:
            message = TASK_FAILURE_MESSAGES.get(task.id)
            if task.status == "completed":
                return _build_crawl_result(True, message or "新闻生成完成，可以前往“我的文章”查看。", task.id, task.processed_articles)
            return _build_crawl_result(False, message or "新闻生成失败：没有成功生成任何文章，请重试。", task.id, task.processed_articles)

        task.status = "processing"
        task.updated_at = utc_now()
        db.commit()

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            task.status = "failed"
            task.updated_at = utc_now()
            db.commit()
            return _build_crawl_result(False, "新闻生成失败：未找到用户。", task_id, 0)

        if not user.openai_api_key:
            task.status = "failed"
            task.updated_at = utc_now()
            db.commit()
            return _build_crawl_result(False, "新闻生成失败：请先在设置中配置AI参数（API Key等）。", task_id, 0)

        if selected_url_list:
            all_news = resolve_feed_items(
                normalized_source,
                selected_urls=selected_url_list,
                limit=max(20, len(selected_url_list)),
            )
        else:
            if normalized_source and normalized_source != DEFAULT_NEWS_SOURCE_URL:
                all_news = fetch_feed_items(normalized_source, limit=5)
            else:
                all_news = fetch_feed_items(normalized_source, limit=5)

        result = _save_articles_from_items(
            db,
            user_id,
            user,
            task,
            all_news,
            success_message="新闻生成完成，可以前往“我的文章”查看。",
            failure_message="新闻生成失败：没有成功生成任何文章，请重试。",
        )
        return result
    except Exception as e:
        failure_message = _format_rsshub_failure_message(e, f"新闻生成失败：{str(e)}")
        log_with_time(f"❌ 后台处理失败: {e}")
        import traceback

        traceback.print_exc()
        if task:
            task.status = "failed"
            task.updated_at = utc_now()
            db.commit()
        if task:
            try:
                create_notification(
                    db,
                    user_id=user_id,
                    type="news_failed",
                    title="新闻生成失败",
                    message=failure_message,
                    source_task_id=task.id,
                    source_url="/news_center",
                )
            except Exception as notify_error:
                log_with_time(f"❌ 写入异常失败通知失败 task_id={task.id}: {notify_error}", level="ERROR")
            return _build_crawl_result(False, failure_message, task.id, task.processed_articles)
        return _build_crawl_result(False, failure_message, task_id, 0)
    finally:
        db.close()


def crawl_feed(user_id: int, source_url: str | None = None, selected_urls: Iterable[str] | None = None) -> dict:
    """启动后台 RSSHub 订阅源任务。"""
    db = next(get_db())
    selected_url_list = _normalize_selected_urls(selected_urls)
    normalized_source = source_url or DEFAULT_NEWS_SOURCE_URL

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "message": "User not found"}

        if source_url and not normalize_rsshub_source_url(source_url):
            return {"success": False, "message": "URL 无效"}

        task = CrawlTask(
            user_id=user_id,
            status="pending",
            total_articles=0,
            processed_articles=0,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        thread = threading.Thread(
            target=_crawl_feed_background,
            args=(user_id, task.id, normalized_source, selected_url_list or None),
        )
        thread.daemon = True
        thread.start()

        return {
            "success": True,
            "message": "爬虫任务已启动，后台处理中",
            "task_id": task.id,
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "message": f"启动失败: {str(e)}"}
    finally:
        db.close()


def crawl_custom_url(user_id: int, url: str, selected_urls: Iterable[str] | None = None) -> dict:
    """抓取任意 RSSHub 路由或订阅源 URL 并生成文章。"""
    return crawl_feed(user_id, source_url=url, selected_urls=selected_urls)


def _crawl_custom_url_background(
    user_id: int,
    task_id: int,
    url: str,
    selected_urls: Iterable[str] | None = None,
) -> None:
    _crawl_feed_background(user_id, task_id, url, selected_urls=selected_urls)


def crawl_and_save_articles_background(
    user_id,
    task_id,
    selected_urls: Iterable[str] | None = None,
):
    """启动后台爬虫任务。"""
    return _crawl_feed_background(user_id, task_id, DEFAULT_NEWS_SOURCE_URL, selected_urls)


def crawl_and_save_articles(
    user_id,
    selected_urls: Iterable[str] | None = None,
    source_url: str | None = None,
):
    """启动后台爬虫任务。"""
    return crawl_feed(user_id, source_url=source_url, selected_urls=selected_urls)
