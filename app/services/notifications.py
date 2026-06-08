from __future__ import annotations

from sqlalchemy.orm import Session

from app.model.models import Notification
from app.utils.time import utc_now


def _notification_payload(notification: Notification) -> dict[str, str | int | bool | None]:
    return {
        "id": notification.id,
        "user_id": notification.user_id,
        "type": notification.type,
        "title": notification.title,
        "message": notification.message,
        "source_task_id": notification.source_task_id,
        "source_url": notification.source_url,
        "is_read": notification.is_read,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
        "updated_at": notification.updated_at.isoformat() if notification.updated_at else None,
    }


def create_notification(
    db: Session,
    *,
    user_id: int,
    type: str,
    title: str,
    message: str,
    source_task_id: int | None = None,
    source_url: str | None = None,
) -> Notification:
    existing = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.type == type,
            Notification.source_task_id == source_task_id,
        )
        .first()
    )
    if existing is not None:
        return existing

    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        source_task_id=source_task_id,
        source_url=source_url,
        is_read=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def list_notifications(db: Session, user_id: int) -> tuple[list[dict[str, str | int | bool | None]], int]:
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .all()
    )
    unread_count = sum(1 for notification in notifications if not notification.is_read)
    return [_notification_payload(notification) for notification in notifications], unread_count


def get_unread_count(db: Session, user_id: int) -> int:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
        .count()
    )


def mark_notifications_read(db: Session, user_id: int, notification_id: int | None = None) -> int:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if notification_id is not None:
        query = query.filter(Notification.id == notification_id)
    else:
        query = query.filter(Notification.is_read.is_(False))

    notifications = query.all()
    affected = 0
    now = utc_now()
    for notification in notifications:
        if notification.is_read:
            continue
        notification.is_read = True
        notification.read_at = now
        notification.updated_at = now
        affected += 1

    if affected > 0:
        db.commit()
    return affected
