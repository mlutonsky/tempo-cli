import json
import subprocess

import pytest

from _helpers import CompletedProc
from tempo_cli import acli
from tempo_cli.errors import ResolutionError


def test_project_id_for_key_caches(patch_acli):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return CompletedProc(stdout=json.dumps({"id": "10802", "key": "STAN"}))

    patch_acli(run)
    assert acli.project_id_for_key("STAN") == 10802
    assert acli.project_id_for_key("STAN") == 10802  # cached
    assert len(calls) == 1


def test_project_id_for_key_missing(patch_acli):
    patch_acli(lambda args, **kw: CompletedProc(stdout=json.dumps({"key": "STAN"})))
    with pytest.raises(ResolutionError):
        acli.project_id_for_key("STAN")


def test_filter_lookup_numeric_short_circuits(monkeypatch):
    # numeric id must NOT invoke acli
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no call")))
    monkeypatch.setattr(acli.shutil, "which", lambda _: "/usr/bin/acli")
    assert acli.filter_lookup("20416") == (20416, None)


def test_filter_lookup_by_name_my(patch_acli):
    def run(args, **kwargs):
        # First call is --my; return a matching filter
        if "--my" in args:
            return CompletedProc(stdout=json.dumps({"values": [{"id": "20416", "name": "Kanban"}]}))
        return CompletedProc(stdout=json.dumps({"values": []}))

    patch_acli(run)
    assert acli.filter_lookup("Kanban") == (20416, "Kanban")


def test_filter_lookup_not_found(patch_acli):
    patch_acli(lambda args, **kw: CompletedProc(stdout=json.dumps({"values": []})))
    with pytest.raises(ResolutionError):
        acli.filter_lookup("does-not-exist")


def test_display_name_resolves_and_caches(patch_acli):
    calls = []
    payload = [{"key": "X-1", "fields": {"assignee": {"accountId": "557058:abc-1", "displayName": "Alice"}}}]

    def run(args, **kw):
        calls.append(args)
        return CompletedProc(stdout=json.dumps(payload))

    patch_acli(run)
    assert acli.display_name_for("557058:abc-1") == "Alice"
    assert acli.display_name_for("557058:abc-1") == "Alice"  # cached
    assert len(calls) == 1


def test_display_name_no_match_caches_false(patch_acli):
    calls = []

    def run(args, **kw):
        calls.append(args)
        return CompletedProc(stdout=json.dumps([]))

    patch_acli(run)
    assert acli.display_name_for("557058:ghost-id") is None
    assert acli.display_name_for("557058:ghost-id") is None
    # Second call must NOT re-invoke acli
    assert len(calls) == 1


def test_display_name_rejects_unsafe_accountid():
    # Defensive: invalid characters short-circuit without any acli call.
    assert acli.display_name_for("x' OR 1=1 --") is None
