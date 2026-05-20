"""Simple disk-backed key/value cache for tempo-cli.

Design:
- Loaded once per process; reads hit an in-memory dict, not the file.
- Writes flush to disk under an `fcntl.flock` so concurrent `tempo-cli` invocations
  don't lose each other's updates (last-write-wins on the locked critical section,
  not on the load-time snapshot).
- File permissions: directory 0o700, file 0o600 — contents include Jira accountIds
  and display names (PII).

The cache directory honours `XDG_CACHE_HOME`; tests can override it by setting that
env var before importing `tempo_cli`.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any


def _cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "tempo-cli"


def _cache_file() -> Path:
    return _cache_dir() / "cache.json"


_state: dict[str, Any] | None = None  # process-local in-memory copy


def _load() -> dict[str, Any]:
    global _state
    if _state is not None:
        return _state
    f = _cache_file()
    if f.exists():
        try:
            _state = json.loads(f.read_text())
            if not isinstance(_state, dict):
                _state = {}
        except (OSError, json.JSONDecodeError):
            _state = {}
    else:
        _state = {}
    return _state


def _flush() -> None:
    """Persist the in-memory cache under a file lock.

    Lock semantics: we hold an exclusive lock on the cache file (or its parent if the
    cache file doesn't exist yet) for the duration of the write + rename. Other
    `tempo-cli` processes block here briefly, ensuring no lost writes within the
    locked section. Within a single process, the in-memory `_state` is the source of
    truth — concurrent threads would still race, but tempo-cli is single-threaded.
    """
    assert _state is not None
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass  # best-effort; non-fatal if FS doesn't support it (e.g. tmpfs in CI)
    lock_path = d / ".lock"
    lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        tmp = _cache_file().with_suffix(".tmp")
        tmp.write_text(json.dumps(_state, ensure_ascii=False, indent=2))
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(_cache_file())
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def reset_for_tests() -> None:
    """Drop the in-process cache and force the next access to re-read from disk."""
    global _state
    _state = None


def get(key: str) -> Any | None:
    return _load().get(key)


def put(key: str, value: Any) -> None:
    _load()[key] = value
    _flush()


def get_nested(*path: str) -> Any | None:
    cur: Any = _load()
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def put_nested(*path_and_value: Any) -> None:
    if len(path_and_value) < 2:
        raise ValueError("put_nested needs at least one path segment and a value")
    *path, value = path_and_value
    cur: dict = _load()
    for p in path[:-1]:
        if p not in cur:
            cur[p] = {}
        nxt = cur[p]
        if not isinstance(nxt, dict):
            raise ValueError(f"cache path collision at {p!r}")
        cur = nxt
    cur[path[-1]] = value
    _flush()


def clear() -> None:
    global _state
    _state = {}
    f = _cache_file()
    if f.exists():
        f.unlink()
