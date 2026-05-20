from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated, Any

import typer

from .. import acli
from ..client import TempoClient
from ..dates import DateRange, named_period, resolve_range
from ..errors import InputError
from ..output import emit, emit_error, is_table, render_seconds_table
from ..resolve import resolve_filter, resolve_issue_id, resolve_project_id, resolve_user


def _validate_top(name: str, value: int | None) -> None:
    if value is not None and value < 0:
        raise InputError(f"--{name} must be >= 0 (got {value})")

app = typer.Typer(help="Aggregated reports.", no_args_is_help=True)


def _plan_seconds_in_window(plan: dict, window: DateRange) -> int:
    """Total seconds a plan contributes to `window` = secondsPerDay × overlap-day-count.

    Tempo v4 returns `secondsPerDay` (the canonical field). We also accept the legacy
    `plannedSecondsPerDay` for forward compatibility. Days are counted inclusively on
    both ends; weekends/holidays are NOT subtracted (a refinement would intersect with
    /user-schedule).
    """
    per_day = plan.get("secondsPerDay") or plan.get("plannedSecondsPerDay") or 0
    start_s = plan.get("startDate")
    end_s = plan.get("endDate")
    if not per_day or not start_s or not end_s:
        return 0
    try:
        p_start = date.fromisoformat(start_s)
        p_end = date.fromisoformat(end_s)
    except ValueError:
        return 0
    overlap_start = max(p_start, window.start)
    overlap_end = min(p_end, window.end)
    if overlap_start > overlap_end:
        return 0
    days = (overlap_end - overlap_start) // timedelta(days=1) + 1
    return int(per_day) * int(days)


def _period_report(period: str, user: str, *, as_table: bool) -> None:
    try:
        rng = named_period(period)
        acc = resolve_user(user)
        with TempoClient() as client:
            schedule = client.get(
                f"/user-schedule/{acc}",
                params={"from": rng.from_iso, "to": rng.to_iso},
            ) or {}
            worklogs_raw = list(client.paginate(
                f"/worklogs/user/{acc}",
                params={"from": rng.from_iso, "to": rng.to_iso},
            ))
        schedule_days = (schedule.get("results") if isinstance(schedule, dict) else []) or []
        required_total = sum((d.get("requiredSeconds") or 0) for d in schedule_days)
        logged_by_day: dict[str, int] = defaultdict(int)
        for r in worklogs_raw:
            day = r.get("startDate")
            if day:
                logged_by_day[day] += r.get("timeSpentSeconds") or 0
        logged_total = sum(logged_by_day.values())
        by_day = []
        for d in schedule_days:
            day = d.get("date")
            by_day.append({
                "date": day,
                "required": d.get("requiredSeconds") or 0,
                "logged": logged_by_day.get(day, 0),
                "type": d.get("type"),
            })
        data = {
            "period": period,
            "from": rng.from_iso,
            "to": rng.to_iso,
            "user": {"accountId": acc},
            "requiredSeconds": required_total,
            "loggedSeconds": logged_total,
            "balanceSeconds": logged_total - required_total,
            "byDay": by_day,
        }
        emit(
            data,
            as_table=as_table,
            table_renderer=lambda d: render_seconds_table(
                f"{period} {d['from']}..{d['to']} — required {d['requiredSeconds']//60}m / logged {d['loggedSeconds']//60}m",
                [(b["date"], b["logged"]) for b in d["byDay"]],
            ),
        )
    except Exception as e:
        emit_error(e)


@app.command("week")
def week(
    ctx: typer.Context,
    user: Annotated[str, typer.Option("--user")] = "@me",
):
    """Required-vs-logged for the current week (Mon–Sun)."""
    as_table = is_table(ctx)
    _period_report("this-week", user, as_table=as_table)


@app.command("month")
def month(
    ctx: typer.Context,
    user: Annotated[str, typer.Option("--user")] = "@me",
):
    """Required-vs-logged for the current month."""
    as_table = is_table(ctx)
    _period_report("this-month", user, as_table=as_table)


@app.command("by-issue")
def by_issue(
    ctx: typer.Context,
    user: Annotated[str, typer.Option("--user")] = "@me",
    from_: Annotated[str | None, typer.Option("--from")] = None,
    to: Annotated[str | None, typer.Option("--to")] = None,
    top: Annotated[int | None, typer.Option("--top", help="Limit to top-N issues")] = None,
):
    """Top issues by time logged for a user in a window."""
    as_table = is_table(ctx)
    try:
        rng = resolve_range(from_, to)
        acc = resolve_user(user)
        with TempoClient() as client:
            raw = list(client.paginate(
                f"/worklogs/user/{acc}",
                params={"from": rng.from_iso, "to": rng.to_iso},
            ))
        by_id: dict[int, int] = defaultdict(int)
        for r in raw:
            issue = r.get("issue") or {}
            iid = issue.get("id")
            if iid is not None:
                by_id[int(iid)] += r.get("timeSpentSeconds") or 0
        _validate_top("top", top)
        ranked_all = sorted(by_id.items(), key=lambda x: -x[1])
        total = sum(s for _, s in ranked_all)
        ranked = ranked_all[:top] if top is not None else ranked_all
        # Best-effort key resolution for the displayed issues
        items = []
        for iid, secs in ranked:
            try:
                key = acli.issue_key_for_id(iid)
            except Exception:
                key = None
            items.append({"issueId": iid, "issue": key, "seconds": secs})
        data = {
            "user": {"accountId": acc},
            "from": rng.from_iso,
            "to": rng.to_iso,
            "totalSeconds": total,
            "displayedSeconds": sum(it["seconds"] for it in items),
            "byIssue": items,
        }
        emit(
            data,
            as_table=as_table,
            table_renderer=lambda d: render_seconds_table(
                f"by-issue {d['from']}..{d['to']}",
                [(it["issue"] or str(it["issueId"]), it["seconds"]) for it in d["byIssue"]],
            ),
        )
    except Exception as e:
        emit_error(e)


@app.command("by-user")
def by_user(
    ctx: typer.Context,
    issue: Annotated[str, typer.Option("--issue", help="Issue key or numeric id")],
    from_: Annotated[str | None, typer.Option("--from")] = None,
    to: Annotated[str | None, typer.Option("--to")] = None,
):
    """For a given issue, show seconds logged by each user. Manager view."""
    as_table = is_table(ctx)
    try:
        iid = resolve_issue_id(issue)
        params: dict = {}
        if from_ or to:
            rng = resolve_range(from_, to)
            params = {"from": rng.from_iso, "to": rng.to_iso}
        with TempoClient() as client:
            raw = list(client.paginate(f"/worklogs/issue/{iid}", params=params or None))
        by_user_map: dict[str, int] = defaultdict(int)
        for r in raw:
            acc = (r.get("author") or {}).get("accountId") or "unknown"
            by_user_map[acc] += r.get("timeSpentSeconds") or 0
        ranked = []
        for acc, secs in sorted(by_user_map.items(), key=lambda x: -x[1]):
            entry = {"accountId": acc, "seconds": secs}
            name = acli.display_name_for(acc) if acc != "unknown" else None
            if name:
                entry["displayName"] = name
            ranked.append(entry)
        data = {
            "issue": issue,
            "issueId": iid,
            "from": params.get("from"),
            "to": params.get("to"),
            "totalSeconds": sum(it["seconds"] for it in ranked),
            "byUser": ranked,
        }
        emit(
            data,
            as_table=as_table,
            table_renderer=lambda d: render_seconds_table(
                f"by-user on {d['issue']}",
                [(u.get("displayName") or u["accountId"], u["seconds"]) for u in d["byUser"]],
            ),
        )
    except Exception as e:
        emit_error(e)


@app.command("period")
def period(
    ctx: typer.Context,
    user: Annotated[str, typer.Option("--user")] = "@me",
    from_: Annotated[str | None, typer.Option("--from", help="Period start date or shortcut")] = None,
    to: Annotated[str | None, typer.Option("--to")] = None,
    name: Annotated[str | None, typer.Option("--period", help="this-week|last-week|this-month|last-month")] = None,
):
    """Tempo period view: required vs. logged plus approval status.

    Uses /timesheet-approvals/user/{accountId} — Tempo's official period accounting.
    The window is determined by --from/--to or by --period (default: this-month).
    """
    as_table = is_table(ctx)
    try:
        if name:
            rng = named_period(name)
        else:
            rng = resolve_range(from_, to)
        acc = resolve_user(user)
        with TempoClient() as client:
            data = client.get(
                f"/timesheet-approvals/user/{acc}",
                params={"from": rng.from_iso, "to": rng.to_iso},
            ) or {}
        required = data.get("requiredSeconds") or 0
        logged = data.get("timeSpentSeconds") or 0
        status = (data.get("status") or {}).get("key")
        actions = list((data.get("actions") or {}).keys())
        out = {
            "from": rng.from_iso,
            "to": rng.to_iso,
            "user": {"accountId": acc},
            "requiredSeconds": required,
            "loggedSeconds": logged,
            "balanceSeconds": logged - required,
            "status": status,
            "availableActions": actions,
        }
        emit(
            out,
            as_table=as_table,
            table_renderer=lambda d: render_seconds_table(
                f"{d['from']}..{d['to']} — status {d['status']}",
                [("required", d["requiredSeconds"]), ("logged", d["loggedSeconds"])],
            ),
        )
    except Exception as e:
        emit_error(e)


def _rollups(raw: list[dict]) -> dict[str, Any]:
    by_user_map: dict[str, int] = defaultdict(int)
    by_issue_map: dict[int, int] = defaultdict(int)
    total = 0
    for r in raw:
        secs = r.get("timeSpentSeconds") or 0
        total += secs
        acc = (r.get("author") or {}).get("accountId") or "unknown"
        by_user_map[acc] += secs
        iid = (r.get("issue") or {}).get("id")
        if iid is not None:
            by_issue_map[int(iid)] += secs
    by_user = []
    for acc, secs in sorted(by_user_map.items(), key=lambda x: -x[1]):
        entry = {"accountId": acc, "seconds": secs}
        name = acli.display_name_for(acc) if acc != "unknown" else None
        if name:
            entry["displayName"] = name
        by_user.append(entry)
    by_issue = []
    for iid, secs in sorted(by_issue_map.items(), key=lambda x: -x[1]):
        try:
            key = acli.issue_key_for_id(iid)
        except Exception:
            key = None
        by_issue.append({"issueId": iid, "issue": key, "seconds": secs})
    return {
        "totalSeconds": total,
        "count": len(raw),
        "byUser": by_user,
        "byIssue": by_issue,
    }


@app.command("by-project")
def by_project(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project key (e.g. STAN) or numeric id")],
    from_: Annotated[str | None, typer.Option("--from")] = None,
    to: Annotated[str | None, typer.Option("--to")] = None,
    top_users: Annotated[int | None, typer.Option("--top-users")] = None,
    top_issues: Annotated[int | None, typer.Option("--top-issues")] = None,
):
    """All worklogs in a Jira project with by-user and by-issue rollups."""
    as_table = is_table(ctx)
    try:
        _validate_top("top-users", top_users)
        _validate_top("top-issues", top_issues)
        rng = resolve_range(from_, to)
        pid = resolve_project_id(project)
        with TempoClient() as client:
            raw = list(client.paginate(
                f"/worklogs/project/{pid}",
                params={"from": rng.from_iso, "to": rng.to_iso},
            ))
        roll = _rollups(raw)
        if top_users is not None:
            roll["byUser"] = roll["byUser"][:top_users]
        if top_issues is not None:
            roll["byIssue"] = roll["byIssue"][:top_issues]
        roll["displayedUserSeconds"] = sum(u["seconds"] for u in roll["byUser"])
        roll["displayedIssueSeconds"] = sum(it["seconds"] for it in roll["byIssue"])
        out = {
            "project": project,
            "projectId": pid,
            "from": rng.from_iso,
            "to": rng.to_iso,
            **roll,
        }
        emit(
            out,
            as_table=as_table,
            table_renderer=lambda d: render_seconds_table(
                f"project {d['project']} — by user",
                [(u.get("displayName") or u["accountId"], u["seconds"]) for u in d["byUser"]],
            ),
        )
    except Exception as e:
        emit_error(e)


@app.command("by-filter")
def by_filter(
    ctx: typer.Context,
    filter_: Annotated[str, typer.Option("--filter", help="Numeric Jira filter id, or exact filter name (own/favourite)")],
    from_: Annotated[str | None, typer.Option("--from")] = None,
    to: Annotated[str | None, typer.Option("--to")] = None,
    top_users: Annotated[int | None, typer.Option("--top-users")] = None,
    top_issues: Annotated[int | None, typer.Option("--top-issues")] = None,
):
    """Worklogs matching a saved Jira filter (JQL)."""
    as_table = is_table(ctx)
    try:
        _validate_top("top-users", top_users)
        _validate_top("top-issues", top_issues)
        rng = resolve_range(from_, to)
        filter_id, filter_name = resolve_filter(filter_)
        with TempoClient() as client:
            raw = list(client.paginate(
                f"/worklogs/jira-filter/{filter_id}",
                params={"from": rng.from_iso, "to": rng.to_iso},
            ))
        roll = _rollups(raw)
        if top_users is not None:
            roll["byUser"] = roll["byUser"][:top_users]
        if top_issues is not None:
            roll["byIssue"] = roll["byIssue"][:top_issues]
        roll["displayedUserSeconds"] = sum(u["seconds"] for u in roll["byUser"])
        roll["displayedIssueSeconds"] = sum(it["seconds"] for it in roll["byIssue"])
        out = {
            "filterId": filter_id,
            "filterName": filter_name,
            "from": rng.from_iso,
            "to": rng.to_iso,
            **roll,
        }
        emit(
            out,
            as_table=as_table,
            table_renderer=lambda d: render_seconds_table(
                f"filter {d['filterId']} — by user",
                [(u.get("displayName") or u["accountId"], u["seconds"]) for u in d["byUser"]],
            ),
        )
    except Exception as e:
        emit_error(e)


@app.command("plan-vs-actual")
def plan_vs_actual(
    ctx: typer.Context,
    user: Annotated[str, typer.Option("--user")] = "@me",
    from_: Annotated[str | None, typer.Option("--from")] = None,
    to: Annotated[str | None, typer.Option("--to")] = None,
):
    """Compare planned vs. actually-logged time for a user."""
    as_table = is_table(ctx)
    try:
        rng = resolve_range(from_, to)
        acc = resolve_user(user)
        with TempoClient() as client:
            plans = list(client.paginate(
                f"/plans/user/{acc}",
                params={"from": rng.from_iso, "to": rng.to_iso},
            ))
            worklogs = list(client.paginate(
                f"/worklogs/user/{acc}",
                params={"from": rng.from_iso, "to": rng.to_iso},
            ))
        planned = sum(_plan_seconds_in_window(p, rng) for p in plans)
        logged = sum((w.get("timeSpentSeconds") or 0) for w in worklogs)
        emit(
            {
                "from": rng.from_iso,
                "to": rng.to_iso,
                "user": {"accountId": acc},
                "plannedSeconds": planned,
                "loggedSeconds": logged,
                "balanceSeconds": logged - planned,
                "planCount": len(plans),
                "worklogCount": len(worklogs),
            },
            as_table=as_table,
            table_renderer=lambda d: render_seconds_table(
                f"plan vs actual {d['from']}..{d['to']}",
                [("planned", d["plannedSeconds"]), ("logged", d["loggedSeconds"])],
            ),
        )
    except Exception as e:
        emit_error(e)
