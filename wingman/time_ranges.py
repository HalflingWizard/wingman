"""Timezone-aware date range helpers for model search tools."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def _zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except Exception:
        return ZoneInfo("UTC")


def _month_start(year: int, month: int, zone: ZoneInfo) -> datetime:
    return datetime(year, month, 1, tzinfo=zone)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _parse(value: str | None, zone: ZoneInfo) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(UTC)


def resolve_date_range(
    query: str,
    timezone: str,
    date_from: str | None = None,
    date_to: str | None = None,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Resolve explicit ISO dates and a small set of common relative periods."""
    zone = _zone(timezone)
    start = _parse(date_from, zone)
    end = _parse(date_to, zone)
    if start is not None or end is not None:
        return start, end
    local_now = (now or datetime.now(UTC)).astimezone(zone)
    text = query.casefold()
    local_start: datetime | None = None
    local_end: datetime | None = None
    if "yesterday" in text:
        local_start = datetime.combine(local_now.date() - timedelta(days=1), time.min, zone)
        local_end = local_start + timedelta(days=1)
    elif "last week" in text:
        current_monday = local_now.date() - timedelta(days=local_now.weekday())
        local_start = datetime.combine(current_monday - timedelta(days=7), time.min, zone)
        local_end = local_start + timedelta(days=7)
    elif "this month" in text:
        local_start = _month_start(local_now.year, local_now.month, zone)
        next_year, next_month = _next_month(local_now.year, local_now.month)
        local_end = _month_start(next_year, next_month, zone)
    elif "last month" in text:
        previous_month = local_now.month - 1 or 12
        previous_year = local_now.year - (1 if local_now.month == 1 else 0)
        local_start = _month_start(previous_year, previous_month, zone)
        local_end = _month_start(local_now.year, local_now.month, zone)
    else:
        for month in range(1, 13):
            month_name = date(2000, month, 1).strftime("%B").casefold()
            if f"last {month_name}" in text:
                year = local_now.year - (1 if month >= local_now.month else 0)
                local_start = _month_start(year, month, zone)
                next_year, next_month = _next_month(year, month)
                local_end = _month_start(next_year, next_month, zone)
                break
    if local_start is None or local_end is None:
        return None, None
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


def within_range(value: datetime, start: datetime | None, end: datetime | None) -> bool:
    comparable = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return (start is None or comparable >= start) and (end is None or comparable < end)
