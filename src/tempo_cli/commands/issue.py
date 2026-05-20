from __future__ import annotations

from collections import defaultdict
from typing import Annotated

import typer

from .. import acli
from ..client import TempoClient
from ..dates import resolve_range
from ..models import normalise_worklog
from ..output import emit, emit_error, is_table, render_seconds_table
from ..resolve import resolve_issue_id

app = typer.Typer(help="Issue-centric aggregates.", no_args_is_help=True)


@app.command("worklogs")
def worklogs(
    ctx: typer.Context,
    issue: str,
    from_: Annotated[str | None, typer.Option("--from")] = None,
    to: Annotated[str | None, typer.Option("--to")] = None,
):
    """All worklogs on an issue with a per-user rollup.

    Range defaults to a wide window covering the issue's lifetime when --from/--to omitted.
    """
    as_table = is_table(ctx)
    try:
        params: dict = {}
        if from_ or to:
            rng = resolve_range(from_, to)
            params = {"from": rng.from_iso, "to": rng.to_iso}
        iid = resolve_issue_id(issue)
        with TempoClient() as client:
            raw = list(client.paginate(f"/worklogs/issue/{iid}", params=params or None))
        worklogs = [normalise_worklog(r, issue_key=issue) for r in raw]
        by_user_map: dict[str, int] = defaultdict(int)
        for w in worklogs:
            by_user_map[w.get("accountId") or "unknown"] += w.get("seconds") or 0
        by_user = []
        for acc, secs in sorted(by_user_map.items(), key=lambda x: -x[1]):
            entry = {"accountId": acc, "seconds": secs}
            name = acli.display_name_for(acc) if acc != "unknown" else None
            if name:
                entry["displayName"] = name
            by_user.append(entry)
        total = sum((w.get("seconds") or 0) for w in worklogs)
        data = {
            "issue": issue,
            "issueId": iid,
            "from": params.get("from"),
            "to": params.get("to"),
            "totalSeconds": total,
            "count": len(worklogs),
            "byUser": by_user,
            "worklogs": worklogs,
        }
        emit(
            data,
            as_table=as_table,
            table_renderer=lambda d: render_seconds_table(
                f"{d['issue']} — {d['count']} worklogs",
                [(u.get("displayName") or u["accountId"], u["seconds"]) for u in d["byUser"]],
            ),
        )
    except Exception as e:
        emit_error(e)
