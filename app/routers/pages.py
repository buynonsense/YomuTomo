from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers.context import get_current_user
from app.utils.templates import create_templates

templates = create_templates("templates")
router = APIRouter(tags=["主页"])


@router.get(
    "/",
    response_class=HTMLResponse,
    summary="首页",
    description="返回应用首页，用于输入课文与进行 AI 配置。",
)
async def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(request, "index.html", {"user": user})
