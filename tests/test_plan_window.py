from datetime import date

from tempo_cli.commands.report import _plan_seconds_in_window
from tempo_cli.dates import DateRange


def _rng(start: str, end: str) -> DateRange:
    return DateRange(date.fromisoformat(start), date.fromisoformat(end))


def test_full_overlap():
    plan = {"startDate": "2026-05-01", "endDate": "2026-05-05", "secondsPerDay": 14400}
    assert _plan_seconds_in_window(plan, _rng("2026-05-01", "2026-05-31")) == 5 * 14400


def test_partial_overlap_at_start():
    plan = {"startDate": "2026-04-28", "endDate": "2026-05-03", "secondsPerDay": 3600}
    # overlap: May 1-3 inclusive = 3 days
    assert _plan_seconds_in_window(plan, _rng("2026-05-01", "2026-05-31")) == 3 * 3600


def test_partial_overlap_at_end():
    plan = {"startDate": "2026-05-30", "endDate": "2026-06-03", "secondsPerDay": 7200}
    # overlap: May 30-31 = 2 days
    assert _plan_seconds_in_window(plan, _rng("2026-05-01", "2026-05-31")) == 2 * 7200


def test_no_overlap():
    plan = {"startDate": "2026-06-01", "endDate": "2026-06-30", "secondsPerDay": 28800}
    assert _plan_seconds_in_window(plan, _rng("2026-05-01", "2026-05-31")) == 0


def test_legacy_field_name_accepted():
    plan = {"startDate": "2026-05-01", "endDate": "2026-05-01", "plannedSecondsPerDay": 3600}
    assert _plan_seconds_in_window(plan, _rng("2026-05-01", "2026-05-31")) == 3600


def test_missing_seconds_returns_zero():
    plan = {"startDate": "2026-05-01", "endDate": "2026-05-31"}
    assert _plan_seconds_in_window(plan, _rng("2026-05-01", "2026-05-31")) == 0


def test_garbage_dates_return_zero():
    plan = {"startDate": "not-a-date", "endDate": "2026-05-31", "secondsPerDay": 3600}
    assert _plan_seconds_in_window(plan, _rng("2026-05-01", "2026-05-31")) == 0
