"""Append-only audit log for destructive operations.

Every POST/PUT/DELETE issued by the CLI lands here, so a human can reconstruct
what the tool — or the LLM agent driving it — actually did. Lives next to the
cache at `$XDG_CACHE_HOME/tempo-cli/audit.log`.

Format: one JSON object per line, fields:
  ts        — ISO-8601 UTC timestamp
  command   — logical action, e.g. "worklog.add" / "plan.delete"
  method    — HTTP verb
  path      — Tempo API path
  body      — request body (for POST/PUT) or null
  dryRun    — true iff the write was suppressed
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MAX_BYTES = 5 * 1024 * 1024  # rotate at 5 MiB


def _log_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "tempo-cli"


def _log_file() -> Path:
    return _log_dir() / "audit.log"


def _rotate_if_needed(path: Path) -> None:
    try:
        if path.stat().st_size >= _MAX_BYTES:
            path.rename(path.with_suffix(".log.1"))
    except FileNotFoundError:
        pass


def record(
    *,
    command: str,
    method: str,
    path: str,
    body: Any | None = None,
    dry_run: bool = False,
    result: Any | None = None,
) -> None:
    """Append one entry to the audit log. Best-effort — never raises to the caller."""
    try:
        d = _log_dir()
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
        f = _log_file()
        _rotate_if_needed(f)
        entry = {
            "ts": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "command": command,
            "method": method,
            "path": path,
            "body": body,
            "dryRun": dry_run,
        }
        if result is not None:
            entry["result"] = result
        # Open with exclusive perms on first create; subsequent writes inherit.
        existed = f.exists()
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        if not existed:
            try:
                os.chmod(f, 0o600)
            except OSError:
                pass
    except OSError:
        # Audit log must never block real work.
        return


def dry_run_response(command: str, method: str, path: str, body: Any | None) -> dict[str, Any]:
    """Build the standard `--dry-run` JSON payload returned to stdout."""
    return {
        "dryRun": True,
        "command": command,
        "would": {"method": method, "path": path, "body": body},
    }
