from __future__ import annotations

import re

from .errors import InputError

_TOKEN = re.compile(r"(?P<num>\d+(?:\.\d+)?)(?P<unit>[dhms])", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 8 * 3600}


def parse_duration(text: str) -> int:
    """Parse a duration like '1h30m', '90m', '1.5h', '1d' into seconds.

    1d = 8h (fixed; document this in --help).
    """
    if text is None or not text.strip():
        raise InputError("empty duration")
    s = text.strip().lower().replace(" ", "")
    total = 0.0
    pos = 0
    matched = False
    for m in _TOKEN.finditer(s):
        if m.start() != pos:
            raise InputError(f"unrecognised duration fragment: {text!r}")
        total += float(m.group("num")) * _UNIT_SECONDS[m.group("unit").lower()]
        pos = m.end()
        matched = True
    if not matched or pos != len(s):
        raise InputError(
            f"could not parse duration {text!r}; expected forms like '1h', '30m', '1h30m', '1.5h'"
        )
    secs = round(total)
    if secs <= 0:
        raise InputError("duration must be positive")
    return secs


def format_duration(seconds: int) -> str:
    """Inverse: 5400 → '1h30m'. Drops zero components, keeps order d/h/m/s."""
    if seconds < 0:
        return "-" + format_duration(-seconds)
    if seconds == 0:
        return "0m"
    parts: list[str] = []
    for unit, size in (("d", 8 * 3600), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            n, seconds = divmod(seconds, size)
            parts.append(f"{n}{unit}")
    return "".join(parts) or "0m"


def format_hours(seconds: int) -> float:
    return round(seconds / 3600.0, 2)
