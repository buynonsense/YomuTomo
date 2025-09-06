from datetime import datetime
import json
from fastapi import APIRouter, Request, Form, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db import get_db
from app.models import User, Article
from app.services import generate_ruby, extract_vocabulary, translate_to_chinese, generate_title, get_openai_client, generate_emoji, generate_all_content
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
    model: str = Form(None),
    db: Session = Depends(get_db)
):
    final_model = model or settings.OPENAI_MODEL
    # 请求头覆盖 + 环境变量默认
    header_api_key = request.headers.get('X-API-Key')
    header_base_url = request.headers.get('X-Base-URL')
    header_model = request.headers.get('X-Model')
    header_furigana_mode = request.headers.get('X-Furigana-Mode')  # kakasi | hybrid | ai
    if header_model:
        final_model = header_model
    client = get_openai_client(header_api_key, header_base_url)
    print(f"[TRACE] process_text_async model={final_model} header_api_key={'yes' if header_api_key else 'no'} base_url={header_base_url or 'env'} furigana={header_furigana_mode or settings.FURIGANA_MODE}")

    # 选择假名模式，优先头部
    try:
        if header_furigana_mode:
            # 临时覆盖进程配置（仅本次请求用）
            from app.core import config as _cfg
            prev = _cfg.settings.FURIGANA_MODE
            _cfg.settings.FURIGANA_MODE = header_furigana_mode
            try:
                # 使用多线程并发生成所有内容
                ruby_text, vocab, translation, title, emoji = generate_all_content(text, final_model, client)
            finally:
                _cfg.settings.FURIGANA_MODE = prev
        else:
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
    api_key: str = Form(None),
    base_url: str = Form(None),
    model: str = Form(None),
):
    # 从请求头获取配置（优先级：请求头 > 表单 > 环境变量）
    final_api_key = api_key or request.headers.get('X-API-Key') or settings.OPENAI_API_KEY
    final_base_url = base_url or request.headers.get('X-Base-URL') or settings.OPENAI_BASE_URL or "https://api.openai.com/v1"
    final_model = model or request.headers.get('X-Model') or settings.OPENAI_MODEL or "gpt-5-mini"
    
    if not final_api_key:
        return {"success": False, "error": "API Key 未提供"}
    
    try:
        client = get_openai_client(final_api_key, final_base_url)
        # 发送一个简单的测试请求
        response = client.chat.completions.create(
            model=final_model,
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        return {"success": True, "model": final_model}
    except Exception as e:
        return {"success": False, "error": str(e)}


