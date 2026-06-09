from __future__ import annotations

from datetime import datetime, timezone

from app.utils.time import BEIJING, UTC, convert_datetime, datetime_to_isoformat


def test_convert_datetime_converts_utc_datetime_to_beijing():
    value = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)

    converted = convert_datetime(value, BEIJING)
    assert converted is not None
    assert converted.isoformat() == "2026-06-08T18:00:00+08:00"


def test_convert_datetime_treats_naive_datetime_as_utc_when_timezone_is_provided():
    value = datetime(2026, 6, 8, 10, 0)

    converted = convert_datetime(value, BEIJING)
    assert converted is not None
    assert converted.isoformat() == "2026-06-08T18:00:00+08:00"


def test_convert_datetime_returns_none_for_none():
    assert convert_datetime(None, BEIJING) is None


def test_datetime_to_isoformat_defaults_to_utc():
    value = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)

    assert datetime_to_isoformat(value) == "2026-06-08T10:00:00+00:00"


def test_datetime_to_isoformat_keeps_naive_datetime_as_utc_when_defaulting():
    value = datetime(2026, 6, 8, 10, 0)

    assert datetime_to_isoformat(value) == "2026-06-08T10:00:00+00:00"
