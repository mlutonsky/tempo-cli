from __future__ import annotations

from typing import Any


def normalise_worklog(raw: dict[str, Any], *, issue_key: str | None = None) -> dict[str, Any]:
    """Turn a Tempo /worklogs response item into our compact shape."""
    issue = raw.get("issue") or {}
    author = raw.get("author") or {}
    out: dict[str, Any] = {
        "id": raw.get("tempoWorklogId"),
        "issueId": issue.get("id"),
        "accountId": author.get("accountId"),
        "date": raw.get("startDate"),
        "start": raw.get("startTime"),
        "seconds": raw.get("timeSpentSeconds"),
        "billableSeconds": raw.get("billableSeconds"),
        "description": raw.get("description"),
    }
    if issue_key:
        out["issue"] = issue_key
    return out


def normalise_plan(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn a Tempo /plans response item into our compact shape."""
    item = raw.get("planItem") or {}
    assignee = raw.get("assignee") or {}
    return {
        "id": raw.get("id"),
        "startDate": raw.get("startDate"),
        "endDate": raw.get("endDate"),
        "secondsPerDay": raw.get("secondsPerDay") or raw.get("plannedSecondsPerDay"),
        "planItemId": item.get("id"),
        "planItemType": item.get("type"),
        "assigneeId": assignee.get("id") or raw.get("assigneeId"),
        "assigneeType": assignee.get("type"),
        "description": raw.get("description"),
    }


def normalise_team(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn a Tempo /teams response item into our compact shape."""
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "leadAccountId": (raw.get("lead") or {}).get("accountId"),
        "summary": raw.get("summary"),
    }


def normalise_attribute(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn a Tempo /work-attributes response item into our compact shape."""
    return {
        "key": raw.get("key"),
        "name": raw.get("name"),
        "type": raw.get("type"),
        "required": raw.get("required"),
        "staticListValues": raw.get("staticListValues"),
    }
