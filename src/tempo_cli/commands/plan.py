from __future__ import annotations

from typing import Annotated

import typer

from .. import audit
from ..client import TempoClient
from ..dates import parse_date, resolve_range
from ..duration import parse_duration
from ..errors import InputError
from ..models import normalise_plan
from ..output import emit, emit_error
from ..resolve import resolve_issue_id, resolve_project_id, resolve_user

app = typer.Typer(help="Tempo plans (capacity / planned time).", no_args_is_help=True)


@app.command("list")
def list_(
    user: Annotated[str | None, typer.Option("--user", help="`@me` or accountId")] = None,
    team: Annotated[int | None, typer.Option("--team", help="Team id")] = None,
    from_: Annotated[str | None, typer.Option("--from")] = None,
    to: Annotated[str | None, typer.Option("--to")] = None,
):
    """List plans within a window. Filter by --user or --team; default = current user."""
    try:
        rng = resolve_range(from_, to)
        params = {"from": rng.from_iso, "to": rng.to_iso}
        with TempoClient() as client:
            if team is not None:
                path = f"/plans/team/{team}"
            else:
                acc = resolve_user(user or "@me")
                path = f"/plans/user/{acc}"
            raw = list(client.paginate(path, params=params))
        emit(
            {
                "from": rng.from_iso,
                "to": rng.to_iso,
                "count": len(raw),
                "plans": [normalise_plan(p) for p in raw],
            }
        )
    except Exception as e:
        emit_error(e)


@app.command("get")
def get(plan_id: int):
    """Fetch a single plan by id."""
    try:
        with TempoClient() as client:
            raw = client.get(f"/plans/{plan_id}")
        emit(normalise_plan(raw))
    except Exception as e:
        emit_error(e)


def _resolve_plan_item(issue: str | None, project: str | None) -> dict[str, str]:
    if issue and project:
        raise InputError("--issue and --project are mutually exclusive")
    if issue:
        iid = resolve_issue_id(issue)
        return {"id": str(iid), "type": "ISSUE"}
    if project:
        pid = resolve_project_id(project)
        return {"id": str(pid), "type": "PROJECT"}
    raise InputError("plan needs --issue or --project")


@app.command("add")
def add(
    start: Annotated[str, typer.Option("--start", help="Plan start date")],
    end: Annotated[str, typer.Option("--end", help="Plan end date (inclusive)")],
    per_day: Annotated[
        str, typer.Option("--per-day", help="Planned duration per day, e.g. 4h or 30m")
    ],
    issue: Annotated[str | None, typer.Option("--issue")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    user: Annotated[str, typer.Option("--user", help="Assignee, `@me` or accountId")] = "@me",
    team: Annotated[
        int | None, typer.Option("--team", help="Assign to a team instead of a user")
    ] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Print the request that WOULD be sent and exit without writing."
        ),
    ] = False,
):
    """Create a plan. Body shape follows Tempo v4 /plans POST."""
    try:
        plan_item = _resolve_plan_item(issue, project)
        body: dict = {
            "startDate": parse_date(start).isoformat(),
            "endDate": parse_date(end).isoformat(),
            "secondsPerDay": parse_duration(per_day),
            "planItem": plan_item,
        }
        if team is not None:
            body["assignee"] = {"id": str(team), "type": "TEAM"}
        else:
            body["assigneeId"] = resolve_user(user)
        if description:
            body["description"] = description
        if dry_run:
            audit.record(command="plan.add", method="POST", path="/plans", body=body, dry_run=True)
            emit(audit.dry_run_response("plan.add", "POST", "/plans", body))
            return
        with TempoClient() as client:
            raw = client.post("/plans", body)
        audit.record(
            command="plan.add",
            method="POST",
            path="/plans",
            body=body,
            result={"id": raw.get("id") if isinstance(raw, dict) else None},
        )
        emit(normalise_plan(raw))
    except Exception as e:
        emit_error(e)


@app.command("update")
def update(
    plan_id: int,
    start: Annotated[str | None, typer.Option("--start")] = None,
    end: Annotated[str | None, typer.Option("--end")] = None,
    per_day: Annotated[str | None, typer.Option("--per-day")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Print the request that WOULD be sent and exit without writing."
        ),
    ] = False,
):
    """Update mutable fields of an existing plan."""
    try:
        path = f"/plans/{plan_id}"
        with TempoClient() as client:
            current = client.get(path) or {}
            # Trim planItem to the {id, type} pair Tempo's POST/PUT accept.
            current_item = current.get("planItem") or {}
            plan_item = {"id": current_item.get("id"), "type": current_item.get("type")}
            body = {
                "startDate": current.get("startDate"),
                "endDate": current.get("endDate"),
                "secondsPerDay": current.get("secondsPerDay")
                or current.get("plannedSecondsPerDay"),
                "planItem": plan_item,
                "description": current.get("description"),
            }
            # Preserve assignee shape: TEAM plans need the nested object; USER plans want assigneeId.
            assignee = current.get("assignee") or {}
            if assignee.get("type") == "TEAM":
                body["assignee"] = {"id": assignee.get("id"), "type": "TEAM"}
            else:
                body["assigneeId"] = assignee.get("id") or current.get("assigneeId")
            if start is not None:
                body["startDate"] = parse_date(start).isoformat()
            if end is not None:
                body["endDate"] = parse_date(end).isoformat()
            if per_day is not None:
                body["secondsPerDay"] = parse_duration(per_day)
            if description is not None:
                body["description"] = description
            if dry_run:
                audit.record(
                    command="plan.update", method="PUT", path=path, body=body, dry_run=True
                )
                emit(audit.dry_run_response("plan.update", "PUT", path, body))
                return
            raw = client.put(path, body)
        audit.record(
            command="plan.update", method="PUT", path=path, body=body, result={"id": plan_id}
        )
        emit(normalise_plan(raw))
    except Exception as e:
        emit_error(e)


@app.command("delete")
def delete(
    plan_id: int,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Print the request that WOULD be sent and exit without writing."
        ),
    ] = False,
):
    """Delete a plan."""
    try:
        path = f"/plans/{plan_id}"
        if dry_run:
            audit.record(command="plan.delete", method="DELETE", path=path, dry_run=True)
            emit(audit.dry_run_response("plan.delete", "DELETE", path, None))
            return
        with TempoClient() as client:
            client.delete(path)
        audit.record(command="plan.delete", method="DELETE", path=path, result={"id": plan_id})
        emit({"deleted": True, "id": plan_id})
    except Exception as e:
        emit_error(e)
