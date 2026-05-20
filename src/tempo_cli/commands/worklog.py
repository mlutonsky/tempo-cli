from __future__ import annotations

import re
from typing import Annotated

import typer

from .. import audit
from ..client import TempoClient
from ..dates import parse_date, resolve_range
from ..duration import parse_duration
from ..errors import InputError
from ..models import normalise_worklog
from ..output import emit, emit_error, is_table, render_seconds_table
from ..resolve import resolve_issue_id, resolve_user

_START_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _normalise_start_time(value: str) -> str:
    """Validate HH:MM (24h) and return HH:MM:SS. Raises InputError on bad input."""
    if not _START_TIME_RE.match(value):
        raise InputError(f"--start must be HH:MM (24h), got {value!r}")
    return f"{value}:00"


def _parse_attributes(pairs: list[str] | None) -> list[dict[str, str]] | None:
    if not pairs:
        return None
    out = []
    for p in pairs:
        if "=" not in p:
            raise InputError(f"--attribute expects KEY=VALUE, got {p!r}")
        k, _, v = p.partition("=")
        k = k.strip()
        if not k:
            raise InputError(f"--attribute key is empty in {p!r}")
        out.append({"key": k, "value": v})
    return out

app = typer.Typer(help="Worklog CRUD operations.", no_args_is_help=True)


@app.command("list")
def list_(
    ctx: typer.Context,
    issue: Annotated[str | None, typer.Option("--issue", help="Issue key or numeric id")] = None,
    user: Annotated[str, typer.Option("--user", help="`@me` or accountId")] = "@me",
    from_: Annotated[str | None, typer.Option("--from", help="Date or period")] = None,
    to: Annotated[str | None, typer.Option("--to", help="Date or period")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Cap results (default: all)")] = None,
):
    """List worklogs filtered by issue and/or user and date range.

    Default range is 'this-month' if both --from and --to are omitted.
    Either --issue or --user (default `@me`) is used to pick the endpoint.
    """
    as_table = is_table(ctx)
    try:
        rng = resolve_range(from_, to)
        with TempoClient() as client:
            if issue:
                iid = resolve_issue_id(issue)
                results = list(client.paginate(
                    f"/worklogs/issue/{iid}",
                    params={"from": rng.from_iso, "to": rng.to_iso},
                ))
            else:
                acc = resolve_user(user)
                results = list(client.paginate(
                    f"/worklogs/user/{acc}",
                    params={"from": rng.from_iso, "to": rng.to_iso},
                ))
        worklogs = [normalise_worklog(r) for r in results]
        if limit is not None:
            worklogs = worklogs[:limit]
        total = sum((w.get("seconds") or 0) for w in worklogs)
        data = {
            "from": rng.from_iso,
            "to": rng.to_iso,
            "count": len(worklogs),
            "totalSeconds": total,
            "worklogs": worklogs,
        }
        emit(
            data,
            as_table=as_table,
            table_renderer=lambda d: render_seconds_table(
                f"Worklogs {d['from']}..{d['to']} ({d['count']})",
                [(f"{w.get('date')} {w.get('description') or ''}", w.get("seconds") or 0) for w in d["worklogs"]],
            ),
        )
    except Exception as e:
        emit_error(e)


@app.command("get")
def get(worklog_id: int):
    """Fetch a single worklog by tempo id."""
    try:
        with TempoClient() as client:
            raw = client.get(f"/worklogs/{worklog_id}")
        emit(normalise_worklog(raw))
    except Exception as e:
        emit_error(e)


@app.command("add")
def add(
    issue: Annotated[str, typer.Option("--issue", help="Issue key or numeric id")],
    duration: Annotated[str, typer.Option("--duration", help="e.g. 1h30m, 90m, 1.5h")],
    date: Annotated[str, typer.Option("--date", help="today, yesterday, or YYYY-MM-DD")] = "today",
    description: Annotated[str | None, typer.Option("--description")] = None,
    start: Annotated[str | None, typer.Option("--start", help="HH:MM (24h)")] = None,
    user: Annotated[str, typer.Option("--user", help="`@me` or accountId")] = "@me",
    billable: Annotated[int | None, typer.Option("--billable-seconds", help="Defaults to duration")] = None,
    attribute: Annotated[list[str] | None, typer.Option("--attribute", help="Work attribute KEY=VALUE (repeatable)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the request that WOULD be sent and exit without writing.")] = False,
):
    """Create a worklog."""
    try:
        secs = parse_duration(duration)
        d = parse_date(date)
        acc = resolve_user(user)
        iid = resolve_issue_id(issue)
        body = {
            "issueId": iid,
            "timeSpentSeconds": secs,
            "billableSeconds": billable if billable is not None else secs,
            "startDate": d.isoformat(),
            "authorAccountId": acc,
        }
        if start:
            body["startTime"] = _normalise_start_time(start)
        if description:
            body["description"] = description
        attrs = _parse_attributes(attribute)
        if attrs:
            body["attributes"] = attrs
        if dry_run:
            audit.record(command="worklog.add", method="POST", path="/worklogs", body=body, dry_run=True)
            emit(audit.dry_run_response("worklog.add", "POST", "/worklogs", body))
            return
        with TempoClient() as client:
            raw = client.post("/worklogs", body)
        audit.record(command="worklog.add", method="POST", path="/worklogs", body=body, result={"id": raw.get("tempoWorklogId") if isinstance(raw, dict) else None})
        emit(normalise_worklog(raw))
    except Exception as e:
        emit_error(e)


@app.command("update")
def update(
    worklog_id: int,
    duration: Annotated[str | None, typer.Option("--duration")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    date: Annotated[str | None, typer.Option("--date")] = None,
    start: Annotated[str | None, typer.Option("--start")] = None,
    billable: Annotated[int | None, typer.Option("--billable-seconds")] = None,
    attribute: Annotated[list[str] | None, typer.Option("--attribute", help="Work attribute KEY=VALUE (repeatable; replaces all attributes)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the request that WOULD be sent and exit without writing.")] = False,
):
    """Update fields on an existing worklog."""
    try:
        path = f"/worklogs/{worklog_id}"
        with TempoClient() as client:
            current = client.get(path) or {}
            existing_attrs = ((current.get("attributes") or {}).get("values") or [])
            body = {
                "timeSpentSeconds": current.get("timeSpentSeconds"),
                "billableSeconds": current.get("billableSeconds"),
                "startDate": current.get("startDate"),
                "startTime": current.get("startTime"),
                "description": current.get("description"),
                "authorAccountId": (current.get("author") or {}).get("accountId"),
                # Preserve current attributes by default — Tempo PUT is replace, not patch.
                "attributes": [{"key": a.get("key"), "value": a.get("value")} for a in existing_attrs],
            }
            if duration is not None:
                body["timeSpentSeconds"] = parse_duration(duration)
                if billable is None:
                    body["billableSeconds"] = body["timeSpentSeconds"]
            if billable is not None:
                body["billableSeconds"] = billable
            if date is not None:
                body["startDate"] = parse_date(date).isoformat()
            if start is not None:
                body["startTime"] = _normalise_start_time(start)
            if description is not None:
                body["description"] = description
            attrs = _parse_attributes(attribute)
            if attrs is not None:
                body["attributes"] = attrs
            if dry_run:
                audit.record(command="worklog.update", method="PUT", path=path, body=body, dry_run=True)
                emit(audit.dry_run_response("worklog.update", "PUT", path, body))
                return
            raw = client.put(path, body)
        audit.record(command="worklog.update", method="PUT", path=path, body=body, result={"id": worklog_id})
        emit(normalise_worklog(raw))
    except Exception as e:
        emit_error(e)


@app.command("delete")
def delete(
    worklog_id: int,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the request that WOULD be sent and exit without writing.")] = False,
):
    """Delete a worklog by id."""
    try:
        path = f"/worklogs/{worklog_id}"
        if dry_run:
            audit.record(command="worklog.delete", method="DELETE", path=path, dry_run=True)
            emit(audit.dry_run_response("worklog.delete", "DELETE", path, None))
            return
        with TempoClient() as client:
            client.delete(path)
        audit.record(command="worklog.delete", method="DELETE", path=path, result={"id": worklog_id})
        emit({"deleted": True, "id": worklog_id})
    except Exception as e:
        emit_error(e)
