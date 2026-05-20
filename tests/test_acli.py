import json
import subprocess

import pytest

from _helpers import CompletedProc
from tempo_cli import acli
from tempo_cli.errors import AcliError, ResolutionError


def test_issue_id_for_key_caches(patch_acli):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return CompletedProc(stdout=json.dumps({"id": "103012", "key": "STAN-23298"}))

    patch_acli(run)

    assert acli.issue_id_for_key("STAN-23298") == 103012
    assert acli.issue_id_for_key("STAN-23298") == 103012
    assert len(calls) == 1  # cached


def test_issue_id_for_key_missing_id(patch_acli):
    patch_acli(lambda args, **kw: CompletedProc(stdout=json.dumps({"key": "STAN-1"})))
    with pytest.raises(ResolutionError):
        acli.issue_id_for_key("STAN-1")


def test_acli_failure(patch_acli):
    patch_acli(lambda args, **kw: CompletedProc(stdout="", returncode=1, stderr="boom"))
    with pytest.raises(AcliError):
        acli.issue_id_for_key("STAN-1")


def test_my_account_id_from_search(patch_acli, monkeypatch):
    payload = [{"key": "X-1", "fields": {"assignee": {"accountId": "abc"}}}]
    patch_acli(lambda args, **kw: CompletedProc(stdout=json.dumps(payload)))
    assert acli.my_account_id() == "abc"
    # cached: no further subprocess invocations needed
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not call"))
    )
    assert acli.my_account_id() == "abc"


def test_seed_my_account_id(patch_acli):
    acli.seed_my_account_id("seeded-id")
    assert acli.my_account_id() == "seeded-id"
