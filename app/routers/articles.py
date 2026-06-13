import json
from urllib.parse import quote, urlparse
from typing import Optional
from fastapi import APIRouter, Request, Form, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.config import settings
from app.db import get_db
from app.model.models import User, Article
from app.routers.context import get_current_user
from app.services.ai_client_async import AIClient, AIClientError
from app.services import services as service_module
from app.services.notifications import create_notification
from app.services.vocabulary import seed_vocabulary_entries, attach_vocab_state, build_vocabulary_view_rows, toggle_vocabulary_status
from app.services.rsshub_feed import RSSHubFetchError, fetch_rsshub_feed_items, normalize_rsshub_source_url
from app.utils.templates import create_templates
from app.utils.time import datetime_to_isoformat, utc_now

# Backward-compatible module-level aliases for tests and older call sites.
get_openai_client = service_module.get_openai_client
generate_ruby = service_module.generate_ruby
extract_vocabulary = service_module.extract_vocabulary
translate_to_chinese = service_module.translate_to_chinese
generate_title = service_module.generate_title
generate_emoji = service_module.generate_emoji
generate_all_content = service_module.generate_all_content
log_with_time = service_module.log_with_time

router = APIRouter(prefix="", tags=["文章"])


def require_login(request: Request, db: Session) -> Optional[User]:
    user = get_current_user(request, db)
    if not user:
        return None
    return user


def _build_internal_source_url(request: Request, fallback_path: str, query_params: dict[str, str] | None = None) -> str:
    path = fallback_path
    referer = request.headers.get("referer")
    if isinstance(referer, str) and referer:
        try:
            parsed = urlparse(referer)
            if parsed.path:
                path = parsed.path
                if parsed.query:
                    path = f"{path}?{parsed.query}"
        except Exception:
            path = fallback_path

    if query_params:
        encoded = "&".join(f"{quote(str(key))}={quote(str(value))}" for key, value in query_params.items())
        path = f"{path}{'&' if '?' in path else '?'}{encoded}"

    return path


@router.get("/dashboard", response_class=HTMLResponse, summary="我的文章仪表盘")
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码，从1开始"),
    size: int = Query(24, ge=1, le=100, description="每页条目数")
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    # 统计总数
    total_items = db.query(func.count(Article.id)).filter(Article.user_id == user.id).scalar() or 0
    # 计算分页边界
    total_pages = max((total_items + size - 1) // size, 1)
    if page > total_pages:
        page = total_pages  # 超出范围回退到最后一页
    offset = (page - 1) * size
    articles = (
        db.query(Article)
        .filter(Article.user_id == user.id)
        .order_by(Article.updated_at.desc())
        .offset(offset)
        .limit(size)
        .all()
    )
    
    for article in articles:
        article.updated_at_iso = datetime_to_isoformat(article.updated_at)
    
    templates = create_templates("templates")
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "articles": articles,
            "page": page,
            "size": size,
            "total_items": total_items,
            "total_pages": total_pages,
        },
    )


@router.get("/loading", response_class=HTMLResponse, summary="显示处理中页面")
async def show_loading(request: Request, db: Session = Depends(get_db)):
    templates = create_templates("templates")
    user = get_current_user(request, db)
    return templates.TemplateResponse(request, "loading.html", {"user": user})


@router.get("/news_center", response_class=HTMLResponse, summary="RSS 订阅中心")
async def news_center(
    request: Request,
    limit: int = Query(12, ge=1, le=20, description="展示的新闻数量"),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    from spider.rsshub_spider import get_feed_items

    news_items = get_feed_items(limit=limit)
    templates = create_templates("templates")
    return templates.TemplateResponse(
        request,
        "news_center.html",
        {
            "user": user,
            "news_items": news_items,
            "limit": limit,
            "news_count": len(news_items),
            "default_news_source_url": settings.NEWS_CENTER_SOURCE_URL,
        },
    )


@router.post("/preview_rsshub_feed", summary="预览 RSS 订阅源")
async def preview_rsshub_feed(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"success": False, "message": "未登录"}

    try:
        payload = await request.json()
    except Exception:
        payload = None

    raw_source_url = None
    limit = 12
    if isinstance(payload, dict):
        raw_source_url = payload.get("source_url") or payload.get("feed_url") or payload.get("url")
        raw_limit = payload.get("limit")
        if raw_limit is not None:
            try:
                limit = max(1, min(int(raw_limit), 20))
            except Exception:
                limit = 12

    if not isinstance(raw_source_url, str) or not raw_source_url.strip():
        return {"success": False, "message": "请提供有效的 RSS 订阅链接"}

    normalized_source = normalize_rsshub_source_url(raw_source_url)
    if not normalized_source:
        return {"success": False, "message": "请提供有效的 RSSHub 路由或订阅源 URL"}

    try:
        items = fetch_rsshub_feed_items(normalized_source, limit=limit)
        return {
            "success": True,
            "message": "已获取预览结果" if items else "未抓到可用条目",
            "source_url": raw_source_url.strip(),
            "normalized_source_url": normalized_source,
            "items": items,
            "count": len(items),
        }
    except RSSHubFetchError as e:
        log_with_time(f"❌ 预览 RSS 订阅源失败 source_url={raw_source_url}: {e}")
        return {"success": False, "message": str(e), "items": [], "count": 0}
    except Exception as e:
        log_with_time(f"❌ 预览 RSS 订阅源失败 source_url={raw_source_url}: {e}")
        return {"success": False, "message": f"预览失败：{str(e)}", "items": [], "count": 0}


@router.get("/reading_result", response_class=HTMLResponse, summary="显示处理结果")
async def show_result(request: Request, db: Session = Depends(get_db)):
    # 从sessionStorage获取处理结果
    templates = create_templates("templates")
    user = get_current_user(request, db)

    # 这里需要从请求中获取数据，暂时返回一个占位符
    return templates.TemplateResponse(
        request,
        "reading.html",
        {
            "user": user,
            "original": "处理结果将在这里显示",
            "ruby_text": "<p>请刷新页面或重新提交</p>",
            "vocab": [],
            "translation": "处理结果将在这里显示",
            "title": "处理结果",
        },
    )


@router.post("/process_text_async", summary="异步处理日语文本")
async def process_text_async(
    request: Request,
    text: str = Form(..., description="日语课文原文"),
    api_key: str = Form(None, description="OpenAI API Key"),
    base_url: str = Form(None, description="OpenAI Base URL"),
    model: str = Form(None, description="OpenAI Model"),
    db: Session = Depends(get_db)
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Determine API key and base URL: prefer explicit form fields, then headers, then user's stored config
    req_api_key = api_key or request.headers.get('x-api-key') or user.openai_api_key
    req_base_url = base_url or request.headers.get('x-base-url') or user.openai_base_url
    final_model = model or request.headers.get('x-model') or user.openai_model

    # Debug: mask API key to help trace missing-config issues
    try:
        masked = (req_api_key[:6] + '***' + req_api_key[-4:]) if req_api_key and len(req_api_key) > 10 else ('None' if not req_api_key else '***')
        log_with_time(f"[DEBUG] resolved req_api_key={masked}; req_base_url={req_base_url or 'None'}; final_model={final_model}")
    except Exception:
        pass

    # If req_api_key is still empty, attempt to reload user from DB (handles stale session/user object)
    if not req_api_key and user:
        try:
            fresh = db.query(User).filter(User.id == user.id).first()
            if fresh:
                req_api_key = fresh.openai_api_key or req_api_key
                req_base_url = fresh.openai_base_url or req_base_url
                final_model = final_model or fresh.openai_model
                try:
                    masked2 = (req_api_key[:6] + '***' + req_api_key[-4:]) if req_api_key and len(req_api_key) > 10 else ('None' if not req_api_key else '***')
                    log_with_time(f"[DEBUG-fallback] reloaded user.id={user.id} req_api_key={masked2}; req_base_url={req_base_url or 'None'}; final_model={final_model}")
                except Exception:
                    pass
        except Exception:
            pass

    if not req_api_key:
        return {"error": "API Key 未提供"}

    client = get_openai_client(req_api_key, req_base_url)
    log_with_time(f"[TRACE] process_text_async model={final_model} user_id={user.id}")

    try:
        # 使用多线程并发生成所有内容
        ruby_text, vocab, translation, title, emoji = generate_all_content(text, final_model, client)
    except Exception as e:
        # 返回错误信息
        try:
            create_notification(
                db,
                user_id=user.id,
                type="system_error",
                title="系统报错",
                message=f"文章生成失败：{str(e)}",
                source_task_id=None,
                source_url="/",
            )
        except Exception as notify_error:
            log_with_time(f"❌ 写入文章生成失败通知失败 user_id={user.id}: {notify_error}", level="ERROR")
        return {"error": str(e)}

    user = get_current_user(request, db)
    if user:
        article = Article(
            user_id=user.id,
            title=title,
            emoji_cover=emoji,  # 直接使用并发生成的结果
            original=text,
            ruby_html=ruby_text,
            translation=translation,
            vocab_json=json.dumps(vocab, ensure_ascii=False),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        try:
            seed_vocabulary_entries(db, user.id, article.id, vocab)
            db.commit()
        except Exception as e:
            db.rollback()
            log_with_time(f"[VOCAB] seed entries failed article_id={article.id}: {e}", level="ERROR")

        try:
            create_notification(
                db,
                user_id=user.id,
                type="article_generated",
                title="文章生成完成",
                message=f"{title} 已生成完成，可以前往“我的文章”查看。",
                source_task_id=article.id,
                source_url=f"/articles/{article.id}",
            )
        except Exception as notify_error:
            log_with_time(f"❌ 写入文章生成成功通知失败 article_id={article.id}: {notify_error}", level="ERROR")

        return {"redirect_url": f"/articles/{article.id}"}

    # 返回处理结果
    return {
        "ruby_text": ruby_text,
        "vocab": vocab,
        "translation": translation,
        "title": title
    }


@router.get("/articles/{article_id}", response_class=HTMLResponse, summary="查看文章详情")
async def view_article(article_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    article = db.query(Article).filter(Article.id == article_id, Article.user_id == user.id).first()
    if not article:
        return RedirectResponse(url="/dashboard", status_code=303)
    article.updated_at = utc_now()
    db.commit()
    vocab = json.loads(article.vocab_json)
    vocab = attach_vocab_state(db, user.id, vocab)
    highlight_notification = request.query_params.get("highlight_notification", "")
    highlight_article = request.query_params.get("highlight_article", "")
    templates = create_templates("templates")
    return templates.TemplateResponse(
        request,
        "reading.html",
        {
            "user": user,
            "article_id": article.id,
            "original": article.original,
            "ruby_text": article.ruby_html,
            "vocab": vocab,
            "translation": article.translation,
            "title": article.title,
            "source_url": article.source_url,
            "highlight_notification": highlight_notification,
            "highlight_article": highlight_article,
        },
    )


@router.get("/vocabulary", response_class=HTMLResponse, summary="我的生词本")
async def vocabulary_book(request: Request, status: str = Query(None, description="筛选状态"), db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    vocab_rows = build_vocabulary_view_rows(db, user.id, status=status)
    mastered_count = sum(1 for row in vocab_rows if row['status'] == 'mastered')
    learning_count = sum(1 for row in vocab_rows if row['status'] == 'learning')

    templates = create_templates("templates")
    return templates.TemplateResponse(
        request,
        "vocabulary.html",
        {
            "user": user,
            "vocab_rows": vocab_rows,
            "status": status or "all",
            "mastered_count": mastered_count,
            "learning_count": learning_count,
            "total_count": len(vocab_rows),
        },
    )


@router.post("/vocabulary/toggle", summary="切换生词状态")
async def toggle_vocabulary(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        if getattr(request.state, "htmx", False):
            return HTMLResponse('<form class="vocab-toggle-form" disabled></form>', status_code=401)
        return {"success": False, "error": "未登录"}

    is_htmx = getattr(request.state, "htmx", False)

    # Stage 3b: htmx 提交走 form-encoded；其它客户端维持 JSON 协议不变。
    word = ""
    pronunciation = None
    meaning = None
    article_id = None
    mastered = True

    if is_htmx:
        form = await request.form()
        word = (form.get("word") or "").strip()
        pronunciation = form.get("pronunciation") or None
        meaning = form.get("meaning") or None
        article_id_raw = form.get("article_id")
        try:
            article_id = int(article_id_raw) if article_id_raw not in (None, "", "None") else None
        except (TypeError, ValueError):
            article_id = None
        # current_mastered=1 表示已掌握 → 这次点击要"取消掌握"
        current_raw = form.get("current_mastered", "0")
        mastered = False if str(current_raw) in ("1", "true", "True") else True
    else:
        try:
            payload = await request.json()
        except Exception:
            return {"success": False, "error": "请求体格式不正确"}
        word = (payload.get("word") or "").strip()
        pronunciation = payload.get("pronunciation")
        meaning = payload.get("meaning")
        mastered = bool(payload.get("mastered", True))
        article_id = payload.get("article_id")

    try:
        entry = toggle_vocabulary_status(
            db,
            user_id=user.id,
            word=word,
            pronunciation=pronunciation,
            meaning=meaning,
            mastered=mastered,
            article_id=article_id,
        )
    except ValueError as e:
        db.rollback()
        if is_htmx:
            return _vocab_toggle_form_response(
                request,
                word=word,
                pronunciation=pronunciation,
                meaning=meaning,
                article_id=article_id,
                current_mastered=1 if mastered else 0,
                error=str(e),
            )
        return {"success": False, "error": str(e)}
    except Exception as e:
        db.rollback()
        if is_htmx:
            return _vocab_toggle_form_response(
                request,
                word=word,
                pronunciation=pronunciation,
                meaning=meaning,
                article_id=article_id,
                current_mastered=1 if mastered else 0,
                error=f"保存失败: {e}",
            )
        return {"success": False, "error": f"保存失败: {str(e)}"}

    if is_htmx:
        return _vocab_toggle_form_response(
            request,
            word=entry.word,
            pronunciation=pronunciation,
            meaning=meaning,
            article_id=article_id,
            current_mastered=1 if entry.status == "mastered" else 0,
        )
    return {
        "success": True,
        "word": entry.word,
        "status": entry.status,
        "mastered": entry.status == 'mastered',
    }


def _vocab_toggle_form_response(
    request: Request,
    *,
    word: str,
    pronunciation: Optional[str],
    meaning: Optional[str],
    article_id: Optional[int],
    current_mastered: int,
    error: str = "",
):
    """返回生词 toggle 的 htmx 片段，附带 HX-Trigger 事件供前端同步父级 class。"""
    templates = create_templates("templates")
    response = templates.TemplateResponse(
        request,
        "partials/_vocab_toggle_form.html",
        {
            "word": word,
            "pronunciation": pronunciation,
            "meaning": meaning,
            "article_id": article_id,
            "current_mastered": current_mastered,
        },
    )
    trigger: dict = {
        "vocab-toggled": {
            "word": word,
            "mastered": bool(int(current_mastered)),
        }
    }
    if error:
        trigger["vocab-toggle-error"] = {"word": word, "message": error}
    response.headers["HX-Trigger"] = json.dumps(trigger)
    return response


@router.post("/articles/{article_id}/delete", summary="删除文章")
async def delete_article(article_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    article = db.query(Article).filter(Article.id == article_id, Article.user_id == user.id).first()
    if article:
        db.delete(article)
        db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/articles/{article_id}/rename", summary="修改文章标题")
async def rename_article(article_id: int, request: Request, title: str = Form(...), db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    article = db.query(Article).filter(Article.id == article_id, Article.user_id == user.id).first()
    if article and title.strip():
        article.title = title.strip()
        db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/test_ai_config", summary="测试 AI 配置是否有效")
async def test_ai_config(
    request: Request,
    api_key: str = Form(...),
    base_url: str = Form(None),
    model: str = Form(None),
):
    final_model = model

    if not api_key:
        return {"success": False, "error": "API Key 未提供"}

    # Use unified async AI client factory so Gemini (Google) endpoints are handled correctly
    provider = {"api_url": base_url or '', "api_key": api_key, "model": final_model, "extra": {}}
    client = AIClient.factory(provider)
    try:
        resp = await client.chat([{"role": "user", "content": "Hello"}])
        return {"success": True, "model": final_model, "text": resp.get('text')}
    except AIClientError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/crawl_news", summary="爬取订阅源并生成文章")
async def crawl_news(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    source_url = None
    selected_urls: list[str] = []
    try:
        payload = await request.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        raw_source_url = payload.get("source_url") or payload.get("feed_url")
        if isinstance(raw_source_url, str):
            raw_source_url = raw_source_url.strip()
            if raw_source_url:
                normalized_source_url = normalize_rsshub_source_url(raw_source_url)
                if not normalized_source_url:
                    return {"success": False, "message": "请提供有效的 RSSHub 路由或订阅源 URL"}
                source_url = normalized_source_url

        raw_selected = payload.get("news_urls")
        if raw_selected is None:
            raw_selected = payload.get("selected_urls")
        if raw_selected is None and payload.get("news_url"):
            raw_selected = [payload.get("news_url")]
        if isinstance(raw_selected, str):
            raw_selected = [raw_selected]
        if isinstance(raw_selected, list):
            for item in raw_selected:
                if not isinstance(item, str):
                    continue
                value = item.strip()
                if value and value.startswith(("http://", "https://", "rsshub://")):
                    selected_urls.append(value)

    if selected_urls:
        # 保持只抓取有效 URL，避免无效链接污染后台任务
        selected_urls = list(dict.fromkeys(selected_urls))
    
    try:
        # Reload user from DB to get latest config (handles stale session/user object)
        try:
            fresh = db.query(User).filter(User.id == user.id).first()
            if fresh:
                user = fresh
        except Exception:
            pass
        
        # 检查用户是否已配置AI设置
        if not user.openai_api_key:
            return {"success": False, "message": "请先在设置中配置AI参数（API Key等）"}
        
        # 验证AI配置是否有效
        try:
            # Use async AI client directly to avoid asyncio.run() in running event loop
            provider = {"api_url": user.openai_base_url or '', "api_key": user.openai_api_key, "model": user.openai_model, "extra": {}}
            client = AIClient.factory(provider)
            resp = await client.chat([{"role": "user", "content": "Hello"}])
            log_with_time(f"[AI] 配置验证成功: {user.openai_model}")
        except Exception as e:
            return {"success": False, "message": f"AI配置验证失败: {str(e)}"}
        
        from spider.rsshub_spider import crawl_and_save_articles
        result = crawl_and_save_articles(user.id, selected_urls=selected_urls or None, source_url=source_url)
        return result
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/crawl_custom_url", summary="抓取自定义订阅源并生成文章")
async def crawl_custom_url_endpoint(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"success": False, "message": "未登录"}

    source_url = None
    selected_urls: list[str] = []
    try:
        payload = await request.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        raw_url = payload.get("source_url") or payload.get("url") or payload.get("page_url") or payload.get("feed_url")
        if isinstance(raw_url, str):
            normalized_source_url = normalize_rsshub_source_url(raw_url)
            if not normalized_source_url:
                return {"success": False, "message": "请提供有效的 RSSHub 路由或订阅源 URL"}
            source_url = normalized_source_url

        raw_selected = payload.get("selected_urls")
        if raw_selected is None:
            raw_selected = payload.get("news_urls")
        if raw_selected is None and payload.get("news_url"):
            raw_selected = [payload.get("news_url")]
        if isinstance(raw_selected, str):
            raw_selected = [raw_selected]
        if isinstance(raw_selected, list):
            for item in raw_selected:
                if not isinstance(item, str):
                    continue
                value = item.strip()
                if value and value.startswith(("http://", "https://", "rsshub://")):
                    selected_urls.append(value)

    if not source_url:
        return {"success": False, "message": "请提供有效的 URL"}

    if selected_urls:
        selected_urls = list(dict.fromkeys(selected_urls))

    try:
        fresh = db.query(User).filter(User.id == user.id).first()
        if fresh:
            user = fresh

        if not user.openai_api_key:
            return {"success": False, "message": "请先在设置中配置AI参数（API Key等）"}

        provider = {"api_url": user.openai_base_url or '', "api_key": user.openai_api_key, "model": user.openai_model, "extra": {}}
        client = AIClient.factory(provider)
        await client.chat([{"role": "user", "content": "Hello"}])

        from spider.rsshub_spider import crawl_custom_url

        return crawl_custom_url(user.id, source_url, selected_urls=selected_urls or None)
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/get_ai_config", summary="获取用户AI配置状态")
async def get_ai_config(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"error": "未登录"}
    
    return {
        "configured": bool(user.openai_api_key),
        "api_key": user.openai_api_key or "",
        "base_url": user.openai_base_url or "",
        "model": user.openai_model,
        "has_api_key": bool(user.openai_api_key),
        "has_base_url": bool(user.openai_base_url)
    }


@router.post("/save_ai_config", summary="保存用户AI配置")
async def save_ai_config(
    request: Request,
    openai_api_key: str = Form(...),
    openai_base_url: str = Form(None),
    openai_model: str = Form(None),
    db: Session = Depends(get_db)
):
    user = require_login(request, db)
    if not user:
        if getattr(request.state, "htmx", False):
            return _ai_config_feedback_response(request, success=False, message="请先登录")
        return RedirectResponse(url="/login", status_code=303)

    success = False
    message = ""
    try:
        # Use the unified async AI client to validate provider (handles Gemini/Google GL correctly)
        test_model = openai_model
        provider = {"api_url": openai_base_url or '', "api_key": openai_api_key, "model": test_model, "extra": {}}
        client = AIClient.factory(provider)
        try:
            await client.chat([{"role": "user", "content": "Hello"}])
        except AIClientError as e:
            db.rollback()
            message = f"AI配置验证失败: {e}"
            return _ai_config_feedback_response(request, success=False, message=message)

        # save configuration to database
        user.openai_api_key = openai_api_key
        user.openai_base_url = openai_base_url
        user.openai_model = test_model
        db.commit()

        try:
            source_url = _build_internal_source_url(request, "/", {"open_settings": "ai"})
            create_notification(
                db,
                user_id=user.id,
                type="settings_saved",
                title="AI 配置已保存",
                message="AI 配置已保存成功，后续文章生成会使用新的参数。",
                source_task_id=user.id,
                source_url=source_url,
            )
        except Exception as notify_error:
            log_with_time(f"❌ 写入 AI 配置保存通知失败 user_id={user.id}: {notify_error}", level="ERROR")

        success = True
        message = "AI配置保存成功"
    except Exception as e:
        db.rollback()
        message = f"AI配置验证失败: {e}"
        return _ai_config_feedback_response(request, success=False, message=message)

    if getattr(request.state, "htmx", False):
        return _ai_config_feedback_response(request, success=success, message=message)
    return {"success": success, "message": message}


def _ai_config_feedback_response(request: Request, *, success: bool, message: str):
    """构造 AI 配置保存的 htmx 反馈片段，并派发 HX-Trigger 事件。

    - success → ai-config-saved 事件
    - 失败    → ai-config-failed 事件，detail.message 供 toast 使用
    """
    templates = create_templates("templates")
    response = templates.TemplateResponse(
        request,
        "partials/_ai_config_feedback.html",
        {"success": success, "message": message},
    )
    event = "ai-config-saved" if success else "ai-config-failed"
    response.headers["HX-Trigger"] = json.dumps(
        {event: {"message": message}}
    )
    return response


@router.get("/crawl_status", summary="获取爬虫任务状态")
async def get_crawl_status(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"error": "未登录"}

    from app.model.models import CrawlTask
    # 获取用户最新的爬虫任务
    task = db.query(CrawlTask).filter(
        CrawlTask.user_id == user.id
    ).order_by(CrawlTask.created_at.desc()).first()

    if not task:
        return {"status": "no_task"}

    from spider.rsshub_spider import TASK_FAILURE_MESSAGES

    message = TASK_FAILURE_MESSAGES.get(task.id)

    payload = {
        "task_id": task.id,
        "status": task.status,
        "total_articles": task.total_articles,
        "processed_articles": task.processed_articles,
        "created_at": datetime_to_isoformat(task.created_at),
        "updated_at": datetime_to_isoformat(task.updated_at),
    }

    if message:
        payload["message"] = message

    return payload


@router.get("/crawl_queue", summary="获取当前用户的爬取队列（活跃 + 最近已完成）")
async def get_crawl_queue(
    request: Request,
    db: Session = Depends(get_db),
    recent_limit: int = Query(20, ge=1, le=50),
):
    """返回当前用户的爬取队列。

    - active：未完成的任务（pending / processing），按 created_at 升序
    - recent：最近 N 条已完成 / 失败的任务，按 updated_at 降序
    - counts：当前 active 数量，用于前端判断要不要继续轮询
    """
    user = require_login(request, db)
    if not user:
        return {"error": "未登录", "active": [], "recent": [], "counts": {"active": 0}}

    from app.model.models import CrawlTask
    from spider.rsshub_spider import TASK_FAILURE_MESSAGES

    def _serialize(task: CrawlTask) -> dict:
        payload = {
            "task_id": task.id,
            "status": task.status,
            "total_articles": task.total_articles,
            "processed_articles": task.processed_articles,
            "created_at": datetime_to_isoformat(task.created_at),
            "updated_at": datetime_to_isoformat(task.updated_at),
        }
        message = TASK_FAILURE_MESSAGES.get(task.id)
        if message:
            payload["message"] = message
        return payload

    active = (
        db.query(CrawlTask)
        .filter(
            CrawlTask.user_id == user.id,
            CrawlTask.status.in_(("pending", "processing")),
        )
        .order_by(CrawlTask.created_at.asc())
        .all()
    )
    recent = (
        db.query(CrawlTask)
        .filter(
            CrawlTask.user_id == user.id,
            CrawlTask.status.in_(("completed", "failed")),
        )
        .order_by(CrawlTask.updated_at.desc())
        .limit(recent_limit)
        .all()
    )

    return {
        "active": [_serialize(t) for t in active],
        "recent": [_serialize(t) for t in recent],
        "counts": {"active": len(active)},
    }


@router.get("/crawl_queue/partial", response_class=HTMLResponse, summary="爬取队列 htmx 片段（self-polling）")
async def get_crawl_queue_partial(
    request: Request,
    db: Session = Depends(get_db),
    recent_limit: int = Query(5, ge=1, le=20),
):
    """返回爬取队列面板的 HTML 片段，供 htmx `hx-get` 轮询使用。

    - 整个片段本身就是 htmx polling unit，外层 div 带 `hx-get`/`hx-trigger`/`hx-swap="outerHTML"`
    - 通过 HX-Trigger 头派发 `queue-update` 事件，便于前端做导航繁忙态同步
    - 未登录时仍然返回 200 + 空状态片段，避免 htmx 反复重试
    """
    from app.model.models import CrawlTask
    from spider.rsshub_spider import TASK_FAILURE_MESSAGES

    user = require_login(request, db)
    active: list = []
    recent: list = []
    if user:
        active_q = (
            db.query(CrawlTask)
            .filter(
                CrawlTask.user_id == user.id,
                CrawlTask.status.in_(("pending", "processing")),
            )
            .order_by(CrawlTask.created_at.asc())
            .all()
        )
        recent_q = (
            db.query(CrawlTask)
            .filter(
                CrawlTask.user_id == user.id,
                CrawlTask.status.in_(("completed", "failed")),
            )
            .order_by(CrawlTask.updated_at.desc())
            .limit(recent_limit)
            .all()
        )

        def _attach_message(task):
            """把 spider 维护的失败原因挂到 ORM 对象上，供模板读取。"""
            message = TASK_FAILURE_MESSAGES.get(task.id)
            if message:
                # SQLAlchemy 不允许在实例上加新列；改用 setattr on attribute
                setattr(task, "message", message)
            return task

        active = [_attach_message(t) for t in active_q]
        recent = [_attach_message(t) for t in recent_q]

    active_count = len(active)
    templates = create_templates("templates")
    response = templates.TemplateResponse(
        request,
        "partials/_crawl_queue_body.html",
        {
            "active": active,
            "recent": recent,
            "active_count": active_count,
            "recent_count": len(recent),
        },
    )
    # 派发自定义事件，让前端可以更新导航繁忙态
    response.headers["HX-Trigger"] = json.dumps(
        {"queue-update": {"activeCount": active_count}}
    )
    return response


@router.get("/get_user_level", summary="获取用户当前等级")
async def get_user_level(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"error": "未登录"}
    return {"level": user.level}


@router.post("/update_user_level", summary="更新用户等级")
async def update_user_level(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"error": "未登录"}
    
    try:
        data = await request.json()
        level = data.get("level")
        
        if level is None:
            return {"error": "缺少等级参数"}
        
        level = int(level)
        if level < 1 or level > 5:
            return {"error": "等级必须在1-5之间"}
        
        user.level = level
        db.commit()
        return {"message": "等级更新成功"}
    except ValueError:
        return {"error": "等级格式不正确"}
    except Exception as e:
        return {"error": f"更新失败: {str(e)}"}
