from datetime import date

import pytest

from tempo_cli.dates import named_period, parse_date, resolve_range
from tempo_cli.errors import InputError

WED = date(2026, 5, 20)  # a Wednesday


def test_parse_date_keywords():
    assert parse_date("today", today=WED) == WED
    assert parse_date("yesterday", today=WED) == date(2026, 5, 19)


def test_parse_date_iso():
    assert parse_date("2024-01-15") == date(2024, 1, 15)


@pytest.mark.parametrize("bad", ["", "tomorrow", "2024/01/15", "foo"])
def test_parse_date_bad(bad):
    with pytest.raises(InputError):
        parse_date(bad)


def test_resolve_range_default_this_month():
    rng = resolve_range(None, None, today=WED)
    assert rng.start == date(2026, 5, 1)
    assert rng.end == date(2026, 5, 31)


def test_resolve_range_keyword_in_either_slot():
    a = resolve_range("this-week", None, today=WED)
    b = resolve_range(None, "this-week", today=WED)
    assert a == b
    assert a.start == date(2026, 5, 18)
    assert a.end == date(2026, 5, 24)


def test_resolve_range_explicit():
    rng = resolve_range("2026-05-10", "2026-05-12", today=WED)
    assert rng.from_iso == "2026-05-10"
    assert rng.to_iso == "2026-05-12"


def test_resolve_range_inverted_raises():
    with pytest.raises(InputError):
        resolve_range("2026-05-20", "2026-05-10", today=WED)


def test_named_period_last_month():
    rng = named_period("last-month", today=WED)
    assert rng.start == date(2026, 4, 1)
    assert rng.end == date(2026, 4, 30)
