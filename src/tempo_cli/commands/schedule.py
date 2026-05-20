from __future__ import annotations

from typing import Annotated

import typer

from ..client import TempoClient
from ..dates import resolve_range
from ..output import emit, emit_error
from ..resolve import resolve_user


def schedule(
    user: Annotated[str, typer.Option("--user", help="`@me` or accountId")] = "@me",
    from_: Annotated[str | None, typer.Option("--from")] = None,
    to: Annotated[str | None, typer.Option("--to")] = None,
) -> None:
    """Show the work schedule (required seconds per day) for a user in a range.

    Output JSON shape: {user, from, to, totalRequiredSeconds, days: [{date, requiredSeconds, type}, ...]}.
    """
    try:
        rng = resolve_range(from_, to, default="this-week")
        acc = resolve_user(user)
        with TempoClient() as client:
            data = (
                client.get(f"/user-schedule/{acc}", params={"from": rng.from_iso, "to": rng.to_iso})
                or {}
            )
        days = (data.get("results") if isinstance(data, dict) else []) or []
        emit(
            {
                "user": {"accountId": acc},
                "from": rng.from_iso,
                "to": rng.to_iso,
                "totalRequiredSeconds": sum((d.get("requiredSeconds") or 0) for d in days),
                "days": [
                    {
                        "date": d.get("date"),
                        "requiredSeconds": d.get("requiredSeconds"),
                        "type": d.get("type"),
                    }
                    for d in days
                ],
            }
        )
    except Exception as e:
        emit_error(e)
