from __future__ import annotations

from datetime import datetime, timedelta, timezone

UTC = timezone.utc
BEIJING = timezone(timedelta(hours=8))


def utc_now() -> datetime:
    return datetime.now(UTC)


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def to_beijing_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).astimezone(BEIJING)
    return value.astimezone(BEIJING)
