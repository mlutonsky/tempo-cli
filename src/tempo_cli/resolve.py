from __future__ import annotations

import re

from . import acli
from .errors import InputError

# Jira accountIds are opaque tokens. The canonical Cloud shape is "<prefix>:<uuid>"
# (e.g. "557058:d0f5ad31-..."), occasionally just alphanumerics. We accept anything
# that cannot break out of a single-quoted JQL literal or rewrite a URL path:
#  - no '/', '?', '#', ' ', or quote characters
#  - bounded length
_ACCOUNT_ID_RE = re.compile(r"^[A-Za-z0-9:._-]{1,128}$")


def _validate_account_id(account_id: str) -> str:
    if not _ACCOUNT_ID_RE.match(account_id):
        raise InputError(
            f"invalid accountId {account_id!r}; "
            "expected up to 128 chars of [A-Za-z0-9:._-]"
        )
    return account_id


def resolve_user(user: str | None) -> str:
    """Return a Jira accountId given '@me' (or None) or a literal accountId.

    Literal accountIds are validated to a safe character set so they cannot be
    used to inject JQL or rewrite Tempo API URL paths.
    """
    if user is None or user == "@me":
        return acli.my_account_id()
    return _validate_account_id(user)


def resolve_issue_id(key_or_id: str) -> int:
    """Accept STAN-123 or a numeric id (as string or int)."""
    s = str(key_or_id).strip()
    if s.isdigit():
        return int(s)
    return acli.issue_id_for_key(s)


def resolve_issue_key(id_or_key: int | str) -> str:
    if isinstance(id_or_key, int) or (isinstance(id_or_key, str) and id_or_key.isdigit()):
        return acli.issue_key_for_id(int(id_or_key))
    return str(id_or_key)


def resolve_project_id(key_or_id: str) -> int:
    """Accept a project key (e.g. 'STAN') or a numeric id (as string)."""
    s = str(key_or_id).strip()
    if s.isdigit():
        return int(s)
    return acli.project_id_for_key(s)


def resolve_filter(id_or_name: str) -> tuple[int, str | None]:
    """Accept a numeric filter id or an exact filter name from own/favourite filters."""
    return acli.filter_lookup(str(id_or_name).strip())
