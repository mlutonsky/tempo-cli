from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

from .duration import format_duration
from .errors import TempoCliError

_stderr = Console(stderr=True)


def is_table(ctx) -> bool:
    """True if the user passed `--table` on the root app; safe on missing/empty ctx."""
    if ctx is None or not getattr(ctx, "obj", None):
        return False
    return bool(ctx.obj.get("table", False))


def emit_json(data: Any) -> None:
    """Write JSON to stdout. No trailing prompt, ends with newline."""
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2, default=_default)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"not JSON-serialisable: {type(obj).__name__}")


def emit_error(err: TempoCliError | Exception, *, exit_code: int = 1) -> None:
    """Write a structured error to stderr and exit."""
    if isinstance(err, TempoCliError):
        payload = {"error": err.to_dict()}
    else:
        payload = {"error": {"code": "internal_error", "message": str(err)}}
    json.dump(payload, sys.stderr, ensure_ascii=False, indent=2, default=_default)
    sys.stderr.write("\n")
    sys.stderr.flush()
    raise SystemExit(exit_code)


def emit(data: Any, *, table_renderer=None, as_table: bool = False) -> None:
    """Either JSON (default) or a Rich table (if --table and a renderer is provided)."""
    if as_table and table_renderer is not None:
        table_renderer(data)
        return
    emit_json(data)


def render_seconds_table(title: str, rows: list[tuple[str, int]]) -> None:
    """Render a (label, seconds) listing as a 3-col table with h:mm-ish duration."""
    table = Table(title=title)
    table.add_column("Label")
    table.add_column("Duration", justify="right")
    table.add_column("Hours", justify="right")
    total = 0
    for label, secs in rows:
        total += secs
        table.add_row(label, format_duration(secs), f"{secs/3600:.2f}")
    table.add_section()
    table.add_row("TOTAL", format_duration(total), f"{total/3600:.2f}")
    _console = Console()
    _console.print(table)
