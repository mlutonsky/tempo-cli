from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from .errors import InputError

# Default period for any report/list command when both --from and --to are omitted.
# Individual commands may explicitly override (e.g. `schedule` uses "this-week" because
# it's natural to ask about your required hours for the current week, and `issue worklogs`
# passes no range at all to fetch the issue's full lifetime).
DEFAULT_RANGE = "this-month"


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date  # inclusive

    @property
    def from_iso(self) -> str:
        return self.start.isoformat()

    @property
    def to_iso(self) -> str:
        return self.end.isoformat()


def _today() -> date:
    return date.today()


def parse_date(text: str, *, today: date | None = None) -> date:
    """Parse a single date: YYYY-MM-DD, today, yesterday."""
    if text is None or not text.strip():
        raise InputError("empty date")
    t = text.strip().lower()
    now = today or _today()
    if t == "today":
        return now
    if t == "yesterday":
        return now - timedelta(days=1)
    try:
        return date.fromisoformat(t)
    except ValueError as e:
        raise InputError(f"invalid date {text!r}: {e}") from e


def _week_bounds(d: date) -> tuple[date, date]:
    # Monday .. Sunday
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _month_bounds(d: date) -> tuple[date, date]:
    first = d.replace(day=1)
    last = (first + relativedelta(months=1)) - timedelta(days=1)
    return first, last


def resolve_range(
    from_text: str | None,
    to_text: str | None,
    *,
    default: str = DEFAULT_RANGE,
    today: date | None = None,
) -> DateRange:
    """Resolve a (--from, --to) pair into an inclusive DateRange.

    If both are None, returns the named `default` period.
    If only one is given, the other defaults to today.
    Keywords accepted in either slot: today, yesterday, YYYY-MM-DD.
    Single-keyword periods (this-week, last-week, this-month, last-month) may be passed
    via either slot — they expand to the full bounds and override the other slot.
    """
    now = today or _today()
    period_keywords = {
        "this-week": _week_bounds(now),
        "last-week": _week_bounds(now - timedelta(days=7)),
        "this-month": _month_bounds(now),
        "last-month": _month_bounds(now - relativedelta(months=1)),
    }

    if from_text is None and to_text is None:
        start, end = period_keywords[default]
        return DateRange(start, end)

    for slot in (from_text, to_text):
        if slot and slot.strip().lower() in period_keywords:
            start, end = period_keywords[slot.strip().lower()]
            return DateRange(start, end)

    start = parse_date(from_text, today=now) if from_text else now
    end = parse_date(to_text, today=now) if to_text else now
    if start > end:
        raise InputError(f"from-date ({start}) is after to-date ({end})")
    return DateRange(start, end)


def named_period(name: str, *, today: date | None = None) -> DateRange:
    now = today or _today()
    bounds = {
        "this-week": _week_bounds(now),
        "last-week": _week_bounds(now - timedelta(days=7)),
        "this-month": _month_bounds(now),
        "last-month": _month_bounds(now - relativedelta(months=1)),
    }
    if name not in bounds:
        raise InputError(f"unknown period {name!r}")
    start, end = bounds[name]
    return DateRange(start, end)
