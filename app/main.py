from contextlib import asynccontextmanager
import asyncio
import logging
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# 加载环境变量
load_dotenv()
from app.core.config import settings
from app.db import engine, Base
from app.routers import pages
from app.routers import auth
from app.routers import articles
from app.routers import evaluation
from app.routers import notifications
from app.routers import tts as tts_router
from app.services.notifications import create_notification


class ExtensionCompatibilityMiddleware(BaseHTTPMiddleware):
    """中间件来减少Chrome扩展冲突"""

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # 为HTML页面添加有助于密码管理器的头
        if request.url.path in ['/login', '/register'] and isinstance(response, Response):
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response.headers['Permissions-Policy'] = 'clipboard-write=(), clipboard-read=()'

        return response


class HtmxRequestMiddleware(BaseHTTPMiddleware):
    """识别 htmx 请求，把 flag 挂到 request.state 上方便 handler 区分响应形态。"""

    async def dispatch(self, request, call_next):
        # htmx 默认在所有 ajax 请求上设置 HX-Request: true
        # https://htmx.org/reference/#request_headers
        request.state.htmx = request.headers.get('HX-Request', '').lower() == 'true'
        # 透传一些常用的 htmx 头，便于端点做更细粒度控制
        request.state.htmx_target = request.headers.get('HX-Target', '')
        request.state.htmx_trigger = request.headers.get('HX-Trigger', '')
        request.state.htmx_trigger_name = request.headers.get('HX-Trigger-Name', '')
        request.state.htmx_current_url = request.headers.get('HX-Current-URL', '')
        return await call_next(request)


tags_metadata = [
    {"name": "主页", "description": "首页与静态页面相关接口。"},
    {"name": "认证", "description": "用户注册、登录、退出登录。"},
    {"name": "处理", "description": "对课文进行注音、翻译与生词提取。"},
    {"name": "文章", "description": "文章的查看、列表、删除与更新时间刷新。"},
    {"name": "评测", "description": "朗读评测接口。"},
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 延续之前自动建表的行为（仍推荐使用 Alembic 管理迁移）
    # 增加数据库连接重试，避免容器初次启动时短暂不可用导致直接退出
    import sqlalchemy
    retries = int(os.getenv("DB_CONNECT_RETRIES", "10"))
    delay = float(os.getenv("DB_CONNECT_DELAY", "3"))
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            if attempt > 1:
                logging.getLogger("startup").info(f"DB connect succeeded after {attempt} attempts")
            break
        except sqlalchemy.exc.OperationalError as e:
            last_err = e
            logging.getLogger("startup").warning(f"DB connect attempt {attempt}/{retries} failed: {e}")
            await asyncio.sleep(delay)
    else:
        # TODO[TechDebt]: 直接 raise 仍会导致应用退出；后续可改为健康检查失败而非崩溃，或暴露 /startup-wait 诊断端点
        logging.getLogger("startup").error("DB connect failed after retries, raising exception")
        raise last_err

    yield


app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


class _NoCacheStaticFiles(StaticFiles):
    """静态资源默认走 no-cache, 让浏览器每次都回源校验 ETag。

    避免开发期/重构期改 JS/CSS 后用户被陈旧缓存卡住 (e.g. alpine 没起来 / 修了 bridge
    但浏览器还在用旧 JS)。`uvicorn --reload` 会重启 worker, 改完源码用户刷一次即可拿新版。
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        # 强制 revalidate: 浏览器每次都用 If-None-Match 校验 ETag, 命中返回 304,
        # 文件变了就拉新内容。配合 StaticFiles 自带的 ETag/Last-Modified 即可。
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(HtmxRequestMiddleware)
app.add_middleware(ExtensionCompatibilityMiddleware)
app.mount("/static", _NoCacheStaticFiles(directory="static"), name="static")


# 路由注册
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(articles.router)
app.include_router(evaluation.router)
app.include_router(notifications.router)
app.include_router(tts_router.router)


@app.middleware("http")
async def system_error_notification_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        try:
            from app.db import SessionLocal

            db = SessionLocal()
            try:
                user_id = request.session.get("user_id") if hasattr(request, "session") else None
                if user_id:
                    create_notification(
                        db,
                        user_id=int(user_id),
                        type="system_error",
                        title="系统报错",
                        message=f"系统发生异常：{str(exc)}",
                        source_task_id=int(time.time_ns()),
                        source_url=request.url.path,
                    )
            finally:
                db.close()
        except Exception as notify_error:
            logging.getLogger("startup").error(f"写入系统报错通知失败: {notify_error}")

        raise

@app.get('/health')
def health():
    return {'status': 'ok'}
