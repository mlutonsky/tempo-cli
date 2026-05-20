from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

from . import cache
from .errors import AcliError, ResolutionError

ACLI_TIMEOUT = 30.0  # seconds; prevents tempo-cli from hanging on a wedged acli


def _run(args: list[str]) -> dict[str, Any] | list[Any]:
    if shutil.which("acli") is None:
        raise AcliError("acli not found on PATH (install Atlassian CLI and run `acli auth login`)")
    try:
        proc = subprocess.run(
            ["acli", *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=ACLI_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise AcliError(
            f"acli timed out after {ACLI_TIMEOUT:.0f}s",
            details={"args": args},
        ) from e
    except OSError as e:
        raise AcliError(f"failed to run acli: {e}") from e
    if proc.returncode != 0:
        raise AcliError(
            f"acli command failed (exit {proc.returncode})",
            details={"args": args, "stderr": proc.stderr.strip()},
        )
    out = proc.stdout.strip()
    if not out:
        raise AcliError("acli returned empty output", details={"args": args})
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise AcliError(
            f"could not parse acli JSON output: {e}",
            details={"args": args, "stdout_head": out[:200]},
        ) from e


def issue_id_for_key(key: str) -> int:
    """Resolve a Jira issue key (STAN-23298) to its numeric id (103012), caching the result."""
    cached = cache.get_nested("issueKey", key)
    if isinstance(cached, int):
        return cached
    data = _run(["jira", "workitem", "view", key, "--json"])
    if not isinstance(data, dict) or "id" not in data:
        raise ResolutionError(
            f"could not resolve issue id for {key!r}", details={"acli_response": data}
        )
    try:
        issue_id = int(data["id"])
    except (TypeError, ValueError) as e:
        raise ResolutionError(f"acli returned non-integer id for {key!r}") from e
    cache.put_nested("issueKey", key, issue_id)
    cache.put_nested("issueId", str(issue_id), key)
    return issue_id


def issue_key_for_id(issue_id: int | str) -> str:
    """Reverse lookup; uses cache and falls back to JQL search."""
    sid = str(issue_id)
    cached = cache.get_nested("issueId", sid)
    if isinstance(cached, str):
        return cached
    data = _run(["jira", "workitem", "search", "--jql", f"id = {sid}", "--json"])
    issues = _extract_issues(data)
    if not issues:
        raise ResolutionError(f"no issue with id {sid}")
    key = issues[0].get("key")
    if not isinstance(key, str):
        raise ResolutionError(f"acli search did not return a key for id {sid}")
    cache.put_nested("issueId", sid, key)
    cache.put_nested("issueKey", key, int(sid))
    return key


def my_account_id() -> str:
    """Return the current user's Jira accountId. Cached after first call."""
    cached = cache.get("myAccountId")
    if isinstance(cached, str):
        return cached
    data = _run(
        ["jira", "workitem", "search", "--jql", "assignee = currentUser()", "--limit", "1", "--json"]
    )
    issues = _extract_issues(data)
    for issue in issues:
        fields = issue.get("fields") or {}
        assignee = fields.get("assignee") or {}
        acc = assignee.get("accountId")
        if isinstance(acc, str):
            cache.put("myAccountId", acc)
            return acc
    raise ResolutionError(
        "could not infer accountId from acli; assign at least one issue to yourself, "
        "or run `tempo-cli user me --account-id <id>` to seed the cache"
    )


def seed_my_account_id(account_id: str) -> None:
    cache.put("myAccountId", account_id)


def project_id_for_key(key: str) -> int:
    """Resolve a Jira project key (e.g. 'STAN') to its numeric id. Cached."""
    cached = cache.get_nested("projectKey", key)
    if isinstance(cached, int):
        return cached
    data = _run(["jira", "project", "view", "--key", key, "--json"])
    if not isinstance(data, dict) or "id" not in data:
        raise ResolutionError(f"could not resolve project id for {key!r}")
    try:
        pid = int(data["id"])
    except (TypeError, ValueError) as e:
        raise ResolutionError(f"acli returned non-integer project id for {key!r}") from e
    cache.put_nested("projectKey", key, pid)
    return pid


def filter_lookup(filter_id_or_name: str) -> tuple[int, str | None]:
    """Resolve a Jira filter by id (numeric str) or by exact name. Returns (id, name)."""
    s = filter_id_or_name.strip()
    if s.isdigit():
        return int(s), None
    # Search owned + favourite filters
    for flag in ("--my", "--favourite"):
        try:
            data = _run(["jira", "filter", "list", flag, "--json"])
        except AcliError:
            continue
        for item in _extract_values(data):
            if item.get("name") == s:
                try:
                    return int(item["id"]), item.get("name")
                except (KeyError, TypeError, ValueError):
                    continue
    raise ResolutionError(f"no Jira filter matches {filter_id_or_name!r}")


def _extract_values(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("values", "results", "items", "issues"):
            v = data.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


_ACCOUNT_ID_RE = re.compile(r"^[A-Za-z0-9:._-]{1,128}$")


def display_name_for(account_id: str) -> str | None:
    """Resolve a Jira accountId to a human displayName via JQL. Cached.

    Returns None if no issues are visible for this user (e.g. they only log time,
    never get assigned), or if the accountId fails a defensive sanity check.
    """
    if not account_id or not _ACCOUNT_ID_RE.match(account_id):
        return None
    cached = cache.get_nested("accountIdName", account_id)
    if isinstance(cached, str):
        return cached
    # Cache miss flag: explicit None remembered so we don't keep retrying
    if cached is False:
        return None
    try:
        data = _run(
            [
                "jira",
                "workitem",
                "search",
                "--jql",
                f"worklogAuthor = '{account_id}' OR assignee = '{account_id}'",
                "--limit",
                "1",
                "--json",
            ]
        )
    except AcliError:
        return None
    issues = _extract_issues(data)
    for issue in issues:
        fields = issue.get("fields") or {}
        for candidate_key in ("assignee", "reporter", "creator"):
            cand = fields.get(candidate_key) or {}
            if cand.get("accountId") == account_id:
                name = cand.get("displayName")
                if isinstance(name, str) and name:
                    cache.put_nested("accountIdName", account_id, name)
                    return name
    cache.put_nested("accountIdName", account_id, False)
    return None


def _extract_issues(data: Any) -> list[dict[str, Any]]:
    """acli search returns either a list directly or {"issues": [...]} depending on version."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("issues", "results", "items"):
            v = data.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        if "key" in data and "fields" in data:
            return [data]
    return []
