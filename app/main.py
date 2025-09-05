from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import settings
from app.db import engine, Base
from app.routers import pages
from app.routers import auth
from app.routers import articles
from app.routers import evaluation


tags_metadata = [
    {"name": "主页", "description": "首页与静态页面相关接口。"},
    {"name": "认证", "description": "用户注册、登录、退出登录。"},
    {"name": "处理", "description": "对课文进行注音、翻译与生词提取。"},
    {"name": "文章", "description": "文章的查看、列表、删除与更新时间刷新。"},
    {"name": "评测", "description": "朗读评测接口。"},
]

app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
)


app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
async def on_startup():
    # 延续之前自动建表的行为（仍推荐使用 Alembic 管理迁移）
    Base.metadata.create_all(bind=engine)


# 路由注册
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(articles.router)
app.include_router(evaluation.router)

@app.get('/health')
def health():
    return {'status': 'ok'}


