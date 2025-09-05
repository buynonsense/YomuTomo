from datetime import datetime
import json
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Article
from app.services import generate_ruby, extract_vocabulary, translate_to_chinese, generate_title, get_openai_client, generate_emoji
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
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    articles = (
        db.query(Article)
        .filter(Article.user_id == user.id)
        .order_by(Article.updated_at.desc())
        .all()
    )
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "articles": articles})


@router.post("/process_text", response_class=HTMLResponse, summary="处理日语文本")
async def process_text(
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

    # 选择假名模式，优先头部
    if header_furigana_mode:
        # 临时覆盖进程配置（仅本次请求用）
        from app.core import config as _cfg
        prev = _cfg.settings.FURIGANA_MODE
        _cfg.settings.FURIGANA_MODE = header_furigana_mode
        try:
            ruby_text = generate_ruby(text, final_model, client)
        finally:
            _cfg.settings.FURIGANA_MODE = prev
    else:
        ruby_text = generate_ruby(text, final_model, client)
    vocab = extract_vocabulary(text, final_model, client)
    translation = translate_to_chinese(text, final_model, client)
    title = generate_title(text, final_model, client)

    user = get_current_user(request, db)
    if user:
        article = Article(
            user_id=user.id,
            title=title,
            emoji_cover=generate_emoji(text, final_model, client),
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
        return RedirectResponse(url=f"/articles/{article.id}", status_code=303)

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse(
        "reading.html",
        {"request": request, "original": text, "ruby_text": ruby_text, "vocab": vocab, "translation": translation, "title": title}
    )


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


