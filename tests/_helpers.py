"""Shared test helpers. Import directly via `from _helpers import …`
(pyproject's `tool.pytest.ini_options.pythonpath` adds `tests/` to sys.path).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompletedProc:
    """Minimal stand-in for `subprocess.CompletedProcess`, used by acli stubs."""

    stdout: str = ""
    returncode: int = 0
    stderr: str = ""
