from __future__ import annotations

from datetime import datetime, timedelta, timezone

UTC = timezone.utc
BEIJING = timezone(timedelta(hours=8))


def utc_now() -> datetime:
    return datetime.now(UTC)


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def convert_datetime(value: datetime | None, target_tz: timezone | None = None) -> datetime | None:
    if value is None:
        return None

    if target_tz is None:
        return value

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(target_tz)


def to_beijing_time(value: datetime | None) -> datetime | None:
    return convert_datetime(value, BEIJING)


def datetime_to_isoformat(value: datetime | None, target_tz: timezone | None = UTC) -> str | None:
    converted = convert_datetime(value, target_tz)
    if converted is None:
        return None

    return converted.isoformat()
