import pytest

from tempo_cli.duration import format_duration, parse_duration
from tempo_cli.errors import InputError


@pytest.mark.parametrize(
    "text,seconds",
    [
        ("30m", 1800),
        ("1h", 3600),
        ("1h30m", 5400),
        ("90m", 5400),
        ("1.5h", 5400),
        ("1d", 8 * 3600),
        ("1d2h30m", 8 * 3600 + 2 * 3600 + 1800),
        ("45s", 45),
        ("  1H 30M  ", 5400),
    ],
)
def test_parse_duration_valid(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "1", "1x", "h", "-1h", "0m"])
def test_parse_duration_invalid(text):
    with pytest.raises(InputError):
        parse_duration(text)


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "0m"),
        (60, "1m"),
        (5400, "1h30m"),
        (8 * 3600, "1d"),
        (8 * 3600 + 1800, "1d30m"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected
