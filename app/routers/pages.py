from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.routers.context import get_current_user

templates = Jinja2Templates(directory="templates")
router = APIRouter(tags=["主页"])


@router.get("/", response_class=HTMLResponse, summary="首页", description="返回应用首页，用于输入课文与进行 AI 配置。")
async def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(request, "index.html", {"user": user})
