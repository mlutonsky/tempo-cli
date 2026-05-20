from __future__ import annotations

from collections import defaultdict
from typing import Annotated

import typer

from .. import acli
from ..client import TempoClient
from ..dates import resolve_range
from ..models import normalise_worklog
from ..output import emit, emit_error, is_table, render_seconds_table
from ..resolve import resolve_user

app = typer.Typer(help="User-centric queries.", no_args_is_help=True)


@app.command("me")
def me(
    account_id: Annotated[
        str | None,
        typer.Option("--account-id", help="Seed the cache instead of resolving via acli"),
    ] = None,
):
    """Return the current Jira accountId. Cached after first successful lookup.

    Pass --account-id to seed the cache directly (useful when acli search returns nothing
    because you have no assigned issues).
    """
    try:
        if account_id:
            acli.seed_my_account_id(account_id)
            emit({"accountId": account_id, "source": "seeded"})
            return
        acc = acli.my_account_id()
        emit({"accountId": acc, "source": "acli"})
    except Exception as e:
        emit_error(e)


@app.command("worklogs")
def worklogs(
    ctx: typer.Context,
    user: Annotated[str, typer.Option("--user")] = "@me",
    from_: Annotated[str | None, typer.Option("--from")] = None,
    to: Annotated[str | None, typer.Option("--to")] = None,
):
    """All worklogs of a user with by-issue and by-day rollups."""
    as_table = is_table(ctx)
    try:
        rng = resolve_range(from_, to)
        acc = resolve_user(user)
        with TempoClient() as client:
            raw = list(
                client.paginate(
                    f"/worklogs/user/{acc}",
                    params={"from": rng.from_iso, "to": rng.to_iso},
                )
            )
        worklogs = [normalise_worklog(r) for r in raw]
        by_issue: dict[int, int] = defaultdict(int)
        by_day: dict[str, int] = defaultdict(int)
        for w in worklogs:
            iid = w.get("issueId")
            if iid is not None:
                by_issue[iid] += w.get("seconds") or 0
            if w.get("date"):
                by_day[w["date"]] += w.get("seconds") or 0
        total = sum((w.get("seconds") or 0) for w in worklogs)
        data = {
            "user": {"accountId": acc},
            "from": rng.from_iso,
            "to": rng.to_iso,
            "count": len(worklogs),
            "totalSeconds": total,
            "byIssue": [
                {"issueId": iid, "seconds": secs}
                for iid, secs in sorted(by_issue.items(), key=lambda x: -x[1])
            ],
            "byDay": [{"date": d, "seconds": secs} for d, secs in sorted(by_day.items())],
            "worklogs": worklogs,
        }
        emit(
            data,
            as_table=as_table,
            table_renderer=lambda d: render_seconds_table(
                f"{acc} — {d['count']} worklogs, {d['from']}..{d['to']}",
                [(str(it["issueId"]), it["seconds"]) for it in d["byIssue"]],
            ),
        )
    except Exception as e:
        emit_error(e)
