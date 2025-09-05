from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pykakasi
import speech_recognition as sr
import io
import difflib
import openai
import os
import json
from datetime import datetime
from typing import Optional
"""兼容入口

保留：旧部署脚本可能仍引用 `app:app`。
真实入口：`app.main:app`。

TODO[TechDebt]: 保留兼容入口 - 防止旧部署脚本失效 - 逐步统一到 uvicorn app.main:app （确认无旧引用后删除）
"""

from app.main import app  # type: ignore  # noqa
tags_metadata = [
    {"name": "主页", "description": "首页与静态页面相关接口。"},
    {"name": "认证", "description": "用户注册、登录、退出登录。"},
    {"name": "处理", "description": "对课文进行注音、翻译与生词提取。"},
    {"name": "文章", "description": "文章的查看、列表、删除与更新时间刷新。"},
    {"name": "评测", "description": "朗读评测接口。"},
]

# app = FastAPI(
#     title="YomuTomo 日语朗读应用 API",
#     description=(
#         "提供课文注音、翻译、生词提取与朗读评测功能；"
#         "支持用户登录后将生成结果保存为文章，并在仪表盘按更新时间排序。"
#     ),
#     version="1.0.0",
#     openapi_tags=tags_metadata,
#     docs_url="/docs",
#     redoc_url="/redoc",
# )
# app.mount("/static", StaticFiles(directory="static"), name="static")
# templates = Jinja2Templates(directory="templates")

# Session middleware (set SECRET_KEY via env)
# app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret-key-change-me"))

# Database setup (PostgreSQL)
# DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5432/yomu_pg")
# engine = create_engine(DATABASE_URL, pool_pre_ping=True)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base = declarative_base()


# class User(Base):
#     __tablename__ = "users"

#     id = Column(Integer, primary_key=True, index=True)
#     email = Column(String(255), unique=True, nullable=False, index=True)
#     password_hash = Column(String(255), nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

#     articles = relationship("Article", back_populates="user", cascade="all, delete-orphan")


# class Article(Base):
#     __tablename__ = "articles"

#     id = Column(Integer, primary_key=True, index=True)
#     user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
#     title = Column(String(255), nullable=False)
#     original = Column(Text, nullable=False)
#     ruby_html = Column(Text, nullable=False)
#     translation = Column(Text, nullable=False)
#     vocab_json = Column(Text, nullable=False)  # stored as JSON string
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

#     user = relationship("User", back_populates="articles")


# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# def get_db() -> OrmSession:
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()


# def create_db() -> None:
#     Base.metadata.create_all(bind=engine)

# kks = pykakasi.kakasi()

# # 配置OpenAI（请设置环境变量OPENAI_API_KEY或修改此处）
# client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", "your-api-key-here"))

# def generate_ruby(text):
#     result = kks.convert(text)
#     ruby_html = ''
#     for item in result:
#         orig = item['orig']
#         hira = item['hira']
#         if orig == hira:  # 假名或标点
#             ruby_html += orig
#         else:
#             ruby_html += f"<ruby>{orig}<rt>{hira}</rt></ruby>"
#     return ruby_html

# def extract_vocabulary(text, model="gpt-5-mini"):
#     prompt = f"""分析以下日语文本，提取出可能对初学者或中级学习者困难的词语。
# 重点提取：
# - 汉字复合词
# - 生僻词语
# - 专业术语
# - 不常见的表达

# 对于每个词语，请提供：
# - word: 日语词语
# - meaning: 中文释义
# - pronunciation: 罗马音读音

# 返回JSON格式的数组，例如：
# [
#   {{"word": "こんにちは", "meaning": "你好", "pronunciation": "konnichiwa"}},
#   {{"word": "世界", "meaning": "世界", "pronunciation": "sekai"}}
# ]

# 文本：{text}"""
#     try:
#         response = client.chat.completions.create(
#             model=model,
#             messages=[{"role": "user", "content": prompt}]
#         )
#         content = response.choices[0].message.content.strip()
#         # 尝试解析JSON
#         if content.startswith('[') and content.endswith(']'):
#             vocab = json.loads(content)
#             return vocab
#         else:
#             # 如果不是JSON，提取引号内的词并创建基本结构
#             import re
#             words = re.findall(r'"([^"]*)"', content)
#             return [{"word": word, "meaning": "释义待补充", "pronunciation": "读音待补充"} for word in words]
#     except Exception as e:
#         print(f"AI提取生词失败: {e}")
#         return []

# def translate_to_chinese(text, model="gpt-5-mini"):
#     """将日语文本翻译成中文"""
#     prompt = f"""请将以下日语文本翻译成自然、流畅的中文。
# 要求：
# - 保持原文的语气和风格
# - 翻译要准确、易懂
# - 适当处理文化差异
# - 保持段落结构

# 日语文本：{text}

# 请直接返回中文翻译，不要添加其他说明。"""
#     try:
#         response = client.chat.completions.create(
#             model=model,
#             messages=[{"role": "user", "content": prompt}]
#         )
#         translation = response.choices[0].message.content.strip()
#         return translation
#     except Exception as e:
#         print(f"AI翻译失败: {e}")
#         return "翻译失败，请检查AI配置"

# def generate_title(text, model="gpt-5-mini"):
#     """根据课文内容生成简洁中文标题（不超过15个汉字，强制中文）。"""
#     prompt = f"""下面是一段日语课文内容，请你基于主要主题生成一个『简体中文』标题：
# 要求：
# 1. 仅输出简体中文标题本身，不要任何前缀/引号/标点（例如“标题：”或冒号都不要）。
# 2. 长度 6~15 个汉字，尽量精炼概括主题。
# 3. 不要包含日文假名、罗马字、英文字母、数字或特殊符号。
# 4. 不要使用书名号、引号、感叹号、句号等标点。
# 5. 避免太空泛的词（如“故事”“文章”），应具体到语义核心。

# 日语原文（截断前800字符）：\n{text[:800]}\n\n请直接输出标题："""
#     try:
#         response = client.chat.completions.create(
#             model=model,
#             messages=[{"role": "user", "content": prompt}]
#         )
#         title = response.choices[0].message.content.strip()
#         # 清理可能的引号
#         title = title.strip('"“”『』「」')
#         # 如果包含日文假名或拉丁字符，尝试再次转换为中文
#         import re
#         if re.search(r'[\u3040-\u30FF]', title) or re.search(r'[A-Za-z]', title):
#             try:
#                 fix_prompt = f"请将下面这段标题改写成符合要求的纯简体中文（6~15个汉字，无标点，无外文）：{title}\n只输出改写后的标题。"
#                 fix_resp = client.chat.completions.create(
#                     model=model,
#                     messages=[{"role": "user", "content": fix_prompt}]
#                 )
#                 fixed = fix_resp.choices[0].message.content.strip().strip('"“”『』「」')
#                 if fixed:
#                     title = fixed
#             except Exception as _:
#                 pass
#         # 再做长度截断（安全）
#         if len(title) > 15:
#             title = title[:15]
#         # 兜底：若仍为空或不含任何中文，使用默认
#         if not re.search(r'[\u4e00-\u9fff]', title):
#             title = "朗读练习"
#         return title or "朗读练习"
#     except Exception as e:
#         print(f"AI生成标题失败: {e}")
#         return "朗读练习"


# def get_current_user(request: Request, db: OrmSession) -> Optional[User]:
#     user_id = request.session.get("user_id")
#     if not user_id:
#         return None
#     return db.query(User).filter(User.id == user_id).first()


# def require_login(request: Request, db: OrmSession) -> User:
#     user = get_current_user(request, db)
#     if not user:
#         raise RedirectResponse(url="/login", status_code=303)
#     return user

# @app.get("/", response_class=HTMLResponse, tags=["主页"], summary="首页", description="返回应用首页，用于输入课文与进行 AI 配置。")
# async def home(request: Request, db: OrmSession = Depends(get_db)):
#     user = get_current_user(request, db)
#     return templates.TemplateResponse("index.html", {"request": request, "user": user})


# @app.get("/register", response_class=HTMLResponse, tags=["认证"], summary="注册页面", description="返回用户注册页面。")
# async def register_page(request: Request, db: OrmSession = Depends(get_db)):
#     user = get_current_user(request, db)
#     if user:
#         return RedirectResponse(url="/dashboard", status_code=303)
#     return templates.TemplateResponse("register.html", {"request": request})


# @app.post("/register", tags=["认证"], summary="提交注册", description="创建新用户并自动登录。")
# async def register(
#     request: Request,
#     email: str = Form(..., description="邮箱，用作登录账号"),
#     password: str = Form(..., description="密码，将进行哈希存储"),
#     db: OrmSession = Depends(get_db),
# ):
#     existing = db.query(User).filter(User.email == email).first()
#     if existing:
#         return templates.TemplateResponse("register.html", {"request": request, "error": "邮箱已被注册"})
#     password_hash = pwd_context.hash(password)
#     user = User(email=email, password_hash=password_hash)
#     db.add(user)
#     db.commit()
#     db.refresh(user)
#     request.session["user_id"] = user.id
#     return RedirectResponse(url="/dashboard", status_code=303)


# @app.get("/login", response_class=HTMLResponse, tags=["认证"], summary="登录页面", description="返回用户登录页面。")
# async def login_page(request: Request, db: OrmSession = Depends(get_db)):
#     user = get_current_user(request, db)
#     if user:
#         return RedirectResponse(url="/dashboard", status_code=303)
#     return templates.TemplateResponse("login.html", {"request": request})


# @app.post("/login", tags=["认证"], summary="提交登录", description="校验用户邮箱与密码，登录成功后写入会话。")
# async def login(
#     request: Request,
#     email: str = Form(..., description="邮箱"),
#     password: str = Form(..., description="密码"),
#     db: OrmSession = Depends(get_db),
# ):
#     user = db.query(User).filter(User.email == email).first()
#     if not user or not pwd_context.verify(password, user.password_hash):
#         return templates.TemplateResponse("login.html", {"request": request, "error": "邮箱或密码错误"})
#     request.session["user_id"] = user.id
#     return RedirectResponse(url="/dashboard", status_code=303)


# @app.post("/logout", tags=["认证"], summary="退出登录", description="清空会话并跳转到首页。")
# async def logout(request: Request):
#     request.session.clear()
#     return RedirectResponse(url="/", status_code=303)


# @app.get("/dashboard", response_class=HTMLResponse, tags=["文章"], summary="我的文章仪表盘", description="列出当前用户的文章，按最近更新时间倒序排序。")
# async def dashboard(request: Request, db: OrmSession = Depends(get_db)):
#     user = require_login(request, db)
#     articles = (
#         db.query(Article)
#         .filter(Article.user_id == user.id)
#         .order_by(Article.updated_at.desc())
#         .all()
#     )
#     return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "articles": articles})

# @app.post(
#     "/process_text",
#     response_class=HTMLResponse,
#     tags=["处理"],
#     summary="处理日语文本",
#     description=(
#         "将提交的日语课文进行假名注音、生词提取与中文翻译，并生成标题。"
#         "若用户已登录，会自动保存为文章并跳转到详情页面；若未登录，则直接返回预览页面。"
#     ),
# )
# async def process_text(
#     request: Request,
#     text: str = Form(..., description="日语课文原文"),
#     api_key: str = Form(None, description="可选，覆盖默认或环境变量中的 API Key"),
#     base_url: str = Form(None, description="可选，自定义 OpenAI Base URL"),
#     model: str = Form(None, description="可选，模型名称，默认 gpt-5-mini"),
#     db: OrmSession = Depends(get_db)
# ):
#     """处理文本并生成阅读页面。
#     优先顺序：自定义请求头 > 表单字段 > 环境变量默认值。
#     这样前端可以用两种方式传递配置，避免不一致。"""
#     header_api_key = request.headers.get('X-API-Key')
#     header_base_url = request.headers.get('X-Base-URL')
#     header_model = request.headers.get('X-Model')

#     final_api_key = header_api_key or api_key or os.getenv("OPENAI_API_KEY", "")
#     final_base_url = header_base_url or base_url or os.getenv("OPENAI_BASE_URL", "")
#     final_model = header_model or model or os.getenv("OPENAI_MODEL", "gpt-5-mini")

#     # 配置OpenAI客户端
#     global client
#     if final_api_key:
#         try:
#             client = openai.OpenAI(api_key=final_api_key, base_url=final_base_url if final_base_url else None)
#         except Exception as e:
#             print("OpenAI客户端初始化失败:", e)

#     # 处理文本，生成ruby文本
#     ruby_text = generate_ruby(text)
#     # 提取生词
#     vocab = extract_vocabulary(text, final_model)
#     # 生成中文翻译
#     translation = translate_to_chinese(text, final_model)
#     # 生成标题
#     title = generate_title(text, final_model)

#     # 若已登录则保存为文章并跳转详情
#     user = get_current_user(request, db)
#     if user:
#         article = Article(
#             user_id=user.id,
#             title=title,
#             original=text,
#             ruby_html=ruby_text,
#             translation=translation,
#             vocab_json=json.dumps(vocab, ensure_ascii=False),
#             created_at=datetime.utcnow(),
#             updated_at=datetime.utcnow(),
#         )
#         db.add(article)
#         db.commit()
#         db.refresh(article)
#         return RedirectResponse(url=f"/articles/{article.id}", status_code=303)

#     # 未登录则直接展示结果（不保存）
#     return templates.TemplateResponse(
#         "reading.html",
#         {"request": request, "original": text, "ruby_text": ruby_text, "vocab": vocab, "translation": translation, "title": title}
#     )

# @app.post(
#     "/evaluate",
#     tags=["评测"],
#     summary="朗读评测",
#     description="根据原文与识别文本的相似度计算分数（0-100）。",
# )
# async def evaluate(
#     request: Request,
#     original: str = Form(..., description="原始日语文本"),
#     recognized: str = Form(..., description="语音识别得到的文本"),
# ):
#     # 简单评测：相似度
#     similarity = difflib.SequenceMatcher(None, original, recognized).ratio()
#     score = int(similarity * 100)
#     return JSONResponse({"score": score, "similarity": similarity})


# @app.get(
#     "/articles/{article_id}",
#     response_class=HTMLResponse,
#     tags=["文章"],
#     summary="查看文章详情",
#     description="进入文章时会刷新其更新时间，以便在仪表盘置顶。",
# )
# async def view_article(article_id: int, request: Request, db: OrmSession = Depends(get_db)):
#     user = require_login(request, db)
#     article = db.query(Article).filter(Article.id == article_id, Article.user_id == user.id).first()
#     if not article:
#         return RedirectResponse(url="/dashboard", status_code=303)
#     # 进入文章刷新更新时间
#     article.updated_at = datetime.utcnow()
#     db.commit()
#     vocab = json.loads(article.vocab_json)
#     return templates.TemplateResponse(
#         "reading.html",
#         {
#             "request": request,
#             "original": article.original,
#             "ruby_text": article.ruby_html,
#             "vocab": vocab,
#             "translation": article.translation,
#             "title": article.title,
#         },
#     )


# @app.post(
#     "/articles/{article_id}/delete",
#     tags=["文章"],
#     summary="删除文章",
#     description="删除当前用户的一篇文章，并返回仪表盘。",
# )
# async def delete_article(article_id: int, request: Request, db: OrmSession = Depends(get_db)):
#     user = require_login(request, db)
#     article = db.query(Article).filter(Article.id == article_id, Article.user_id == user.id).first()
#     if article:
#         db.delete(article)
#         db.commit()
#     return RedirectResponse(url="/dashboard", status_code=303)


# @app.on_event("startup")
# async def on_startup():
#     create_db()
