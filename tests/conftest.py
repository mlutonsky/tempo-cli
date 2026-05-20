from __future__ import annotations

import subprocess

import pytest


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Redirect XDG_CACHE_HOME so the test suite doesn't touch the real cache.

    The cache module reads XDG_CACHE_HOME lazily on each access, so we just need to
    set the env var and reset the in-process state between tests.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    from tempo_cli import cache

    cache.reset_for_tests()
    yield
    cache.reset_for_tests()


@pytest.fixture
def fake_token(monkeypatch):
    monkeypatch.setenv("TEMPO_API_TOKEN", "test-token")


@pytest.fixture
def patch_acli(monkeypatch):
    """Patch `subprocess.run` (used by tempo_cli.acli._run) with a caller-supplied fn.

    Usage::

        def test_x(patch_acli):
            patch_acli(lambda args, **kw: CompletedProc(stdout=json.dumps({...})))

    Also pins `shutil.which("acli")` so the AcliError early-return is bypassed.
    """
    from tempo_cli import acli

    def _apply(fn):
        monkeypatch.setattr(subprocess, "run", fn)
        monkeypatch.setattr(acli.shutil, "which", lambda _: "/usr/bin/acli")

    return _apply
