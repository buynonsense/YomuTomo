from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.services import hash_password, verify_password

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="", tags=["认证"])


def get_current_user(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


@router.get("/register", response_class=HTMLResponse, summary="注册页面")
async def register_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register", summary="提交注册")
async def register(
    request: Request,
    email: str = Form(..., description="邮箱，用作登录账号"),
    password: str = Form(..., description="密码，将进行哈希存储"),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse("register.html", {"request": request, "error": "邮箱已被注册"})
    password_hash = hash_password(password)
    user = User(email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/login", response_class=HTMLResponse, summary="登录页面")
async def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", summary="提交登录")
async def login(
    request: Request,
    email: str = Form(..., description="邮箱"),
    password: str = Form(..., description="密码"),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "邮箱或密码错误"})
    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/logout", summary="退出登录")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


