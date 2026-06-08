from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers.context import get_current_user
from app.services.notifications import get_unread_count, list_notifications, mark_notifications_read

router = APIRouter(prefix="", tags=["通知"])


def require_login(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        return None
    return user


@router.get("/notifications", summary="获取通知列表")
async def get_notifications(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"success": False, "message": "未登录"}

    items, unread_count = list_notifications(db, user.id)
    return {"success": True, "items": items, "unread_count": unread_count}


@router.get("/notifications/unread-count", summary="获取未读通知数")
async def get_notifications_unread_count(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"success": False, "message": "未登录", "unread_count": 0}

    return {"success": True, "unread_count": get_unread_count(db, user.id)}


@router.post("/notifications/mark-read", summary="标记通知已读")
async def mark_notifications_read_endpoint(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return {"success": False, "message": "未登录", "affected": 0}

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    notification_id = None
    if isinstance(payload, dict):
        if payload.get("all") is True:
            notification_id = None
        else:
            raw_notification_id = payload.get("notification_id")
            if isinstance(raw_notification_id, int):
                notification_id = raw_notification_id
            elif isinstance(raw_notification_id, str) and raw_notification_id.isdigit():
                notification_id = int(raw_notification_id)

    affected = mark_notifications_read(db, user.id, notification_id)
    return {"success": True, "affected": affected}
