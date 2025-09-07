from datetime import datetime
import json
from fastapi import APIRouter, Request, Form, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db import get_db
from app.model.models import User, Article
from app.services.services import generate_ruby, extract_vocabulary, translate_to_chinese, generate_title, get_openai_client, generate_emoji, generate_all_content
from app.services.ai_client_async import AIClient, AIClientError
from app.core.config import settings

router = APIRouter(prefix="", tags=["文章"])


def get_current_user(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_login(request: Request, db: Session) -> User | None:
    user = get_current_user(request, db)
    if not user:
        return None
    return user


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
    
    # 转换时间为北京时间
    from datetime import timedelta
    for article in articles:
        if article.updated_at:
            article.updated_at_beijing = article.updated_at + timedelta(hours=8)
        else:
            article.updated_at_beijing = None
    
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "articles": articles,
            "page": page,
            "size": size,
            "total_items": total_items,
            "total_pages": total_pages,
        },
    )


@router.get("/loading", response_class=HTMLResponse, summary="显示处理中页面")
async def show_loading(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse("loading.html", {"request": request})


@router.get("/reading_result", response_class=HTMLResponse, summary="显示处理结果")
async def show_result(request: Request):
    # 从sessionStorage获取处理结果
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")

    # 这里需要从请求中获取数据，暂时返回一个占位符
    return templates.TemplateResponse(
        "reading.html",
        {
            "request": request,
            "original": "处理结果将在这里显示",
            "ruby_text": "<p>请刷新页面或重新提交</p>",
            "vocab": [],
            "translation": "处理结果将在这里显示",
            "title": "处理结果"
        }
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
        print(f"[DEBUG] resolved req_api_key={masked}; req_base_url={req_base_url or 'None'}; final_model={final_model}")
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
                    print(f"[DEBUG-fallback] reloaded user.id={user.id} req_api_key={masked2}; req_base_url={req_base_url or 'None'}; final_model={final_model}")
                except Exception:
                    pass
        except Exception:
            pass

    if not req_api_key:
        return {"error": "API Key 未提供"}

    client = get_openai_client(req_api_key, req_base_url)
    print(f"[TRACE] process_text_async model={final_model} user_id={user.id}")

    try:
        # 使用多线程并发生成所有内容
        ruby_text, vocab, translation, title, emoji = generate_all_content(text, final_model, client)
    except Exception as e:
        # 返回错误信息
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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(article)
        db.commit()
        db.refresh(article)
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
    article.updated_at = datetime.utcnow()
    db.commit()
    vocab = json.loads(article.vocab_json)
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse(
        "reading.html",
        {
            "request": request,
            "original": article.original,
            "ruby_text": article.ruby_html,
            "vocab": vocab,
            "translation": article.translation,
            "title": article.title,
            "source_url": article.source_url,
        },
    )


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


@router.post("/crawl_news", summary="爬取NHK新闻并生成文章")
async def crawl_news(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
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
            print(f"[AI] 配置验证成功: {user.openai_model}")
        except Exception as e:
            return {"success": False, "message": f"AI配置验证失败: {str(e)}"}
        
        from spider.nhk_spider import crawl_and_save_articles
        result = crawl_and_save_articles(user.id)
        return result
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
        return RedirectResponse(url="/login", status_code=303)
    
    try:
        # Use the unified async AI client to validate provider (handles Gemini/Google GL correctly)
        test_model = openai_model
        provider = {"api_url": openai_base_url or '', "api_key": openai_api_key, "model": test_model, "extra": {}}
        client = AIClient.factory(provider)
        try:
            resp = await client.chat([{"role": "user", "content": "Hello"}])
        except AIClientError as e:
            db.rollback()
            return {"success": False, "message": f"AI配置验证失败: {str(e)}"}

        # save configuration to database
        user.openai_api_key = openai_api_key
        user.openai_base_url = openai_base_url
        user.openai_model = test_model
        db.commit()
        return {"success": True, "message": "AI配置保存成功"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": f"AI配置验证失败: {str(e)}"}


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
    
    return {
        "task_id": task.id,
        "status": task.status,
        "total_articles": task.total_articles,
        "processed_articles": task.processed_articles,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat()
    }


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


