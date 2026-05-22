"""Tests for metering query window calculation (no Home Assistant import)."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PORTAL_TIMEZONE = "Europe/Zurich"

try:
    _PORTAL_TZ: ZoneInfo | timezone = ZoneInfo(PORTAL_TIMEZONE)
except ZoneInfoNotFoundError:
    _PORTAL_TZ = timezone(timedelta(hours=2))  # CEST stand-in for dev without tzdata


def _portal_tz() -> ZoneInfo | timezone:
    return _PORTAL_TZ


def now_in_portal_tz(now: datetime | None = None) -> datetime:
    tz = _portal_tz()
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def swiss_portal_day_end_local(swiss_day: date) -> datetime:
    tz = _portal_tz()
    start_next_day = datetime.combine(
        swiss_day + timedelta(days=1), time.min, tzinfo=tz
    )
    return start_next_day - timedelta(milliseconds=1)


def swiss_portal_day_end_utc(swiss_day: date) -> datetime:
    return swiss_portal_day_end_local(swiss_day).astimezone(timezone.utc)


def is_swiss_portal_day_published(now: datetime, swiss_day: date) -> bool:
    return now_in_portal_tz(now).date() > swiss_day


def get_polling_day(now: datetime | None = None) -> date:
    now_local = now_in_portal_tz(now)
    today = now_local.date()
    if is_swiss_portal_day_published(now_local, today):
        return today
    return today - timedelta(days=1)


def p1d_window_for_swiss_day(
    swiss_day: date,
) -> tuple[datetime, datetime, datetime, datetime]:
    tz = _portal_tz()
    start_swiss = datetime.combine(swiss_day, time.min, tzinfo=tz)
    start_utc = start_swiss.astimezone(timezone.utc)
    stop_swiss = swiss_portal_day_end_local(swiss_day)
    stop_utc = stop_swiss.astimezone(timezone.utc)
    return start_utc, stop_utc, start_swiss, stop_swiss


def _format_validity_start(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _format_validity_stop_dt(stop: datetime) -> str:
    return stop.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.999Z")


def test_polling_day_uses_swiss_calendar() -> None:
    """2026-05-22 13:00 UTC = 15:00 CEST → latest published Swiss day is 2026-05-21."""
    now = datetime(2026, 5, 22, 13, 0, 0, tzinfo=timezone.utc)
    assert get_polling_day(now=now) == date(2026, 5, 21)


def test_polling_day_after_midnight_swiss() -> None:
    """After midnight Swiss on 23 May, day 22 May is published."""
    now = datetime(2026, 5, 22, 22, 0, 0, tzinfo=timezone.utc)
    assert get_polling_day(now=now) == date(2026, 5, 22)


def test_p1d_window_matches_browser_day_chart() -> None:
    """Swiss 2026-05-21 (CEST) → API UTC validity range from my.bkw.ch."""
    start_utc, stop_utc, start_swiss, stop_swiss = p1d_window_for_swiss_day(
        date(2026, 5, 21)
    )
    assert _format_validity_start(start_utc) == "2026-05-20T22:00:00.000Z"
    assert _format_validity_stop_dt(stop_utc) == "2026-05-21T21:59:59.999Z"
    assert start_swiss.hour == 0 and start_swiss.day == 21
    assert stop_swiss.hour == 23 and stop_swiss.minute == 59


if __name__ == "__main__":
    test_polling_day_uses_swiss_calendar()
    test_polling_day_after_midnight_swiss()
    test_p1d_window_matches_browser_day_chart()
    print("ok")
