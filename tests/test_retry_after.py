from datetime import UTC, datetime, timedelta

from tempo_cli.client import RETRY_DELAY_CAP, _parse_retry_after


def test_missing_uses_fallback():
    assert _parse_retry_after(None, 2.5) == 2.5


def test_delta_seconds():
    assert _parse_retry_after("12", 1.0) == 12.0
    assert _parse_retry_after("0", 5.0) == 0.0


def test_http_date_format():
    soon = datetime.now(tz=UTC) + timedelta(seconds=30)
    header = soon.strftime("%a, %d %b %Y %H:%M:%S GMT")
    out = _parse_retry_after(header, 1.0)
    # ~30s ± parsing jitter
    assert 25 <= out <= 35


def test_garbage_falls_back():
    assert _parse_retry_after("not a date or number", 4.0) == 4.0


def test_clamp_huge():
    assert _parse_retry_after("999999", 1.0) == RETRY_DELAY_CAP


def test_clamp_negative_zero():
    # past HTTP-date → negative seconds → clamped to 0
    past = datetime.now(tz=UTC) - timedelta(hours=1)
    header = past.strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert _parse_retry_after(header, 5.0) == 0.0
