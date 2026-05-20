"""End-to-end tests of the JSON output / error contract through the CLI entry point."""

import json
import sys

from tempo_cli.cli import main


def _run(monkeypatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["tempo-cli", *argv])
    try:
        main()
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    return 0


def test_version_emits_json(monkeypatch, capsys):
    rc = _run(monkeypatch, ["--version"])
    out, err = capsys.readouterr()
    assert rc == 0
    payload = json.loads(out)
    assert payload["name"] == "tempo-cli"
    assert "version" in payload


def test_missing_required_option_emits_json_error(monkeypatch, capsys):
    # `worklog add` without --duration → Click MissingParameter → JSON error envelope on stderr
    rc = _run(monkeypatch, ["worklog", "add", "--issue", "X"])
    out, err = capsys.readouterr()
    assert rc != 0
    payload = json.loads(err)  # MUST be valid JSON, not plain text
    assert payload["error"]["code"] == "input_error"
    assert "Missing option" in payload["error"]["message"] or "duration" in payload["error"]["message"].lower()
    assert out == ""  # stdout stays clean on error


def test_unknown_subcommand_emits_json_error(monkeypatch, capsys):
    rc = _run(monkeypatch, ["nope-not-real"])
    out, err = capsys.readouterr()
    assert rc != 0
    payload = json.loads(err)
    assert payload["error"]["code"] == "input_error"


def test_agent_guide_emits_json_envelope(monkeypatch, capsys):
    rc = _run(monkeypatch, ["agent-guide"])
    out, err = capsys.readouterr()
    assert rc == 0
    payload = json.loads(out)
    assert "path" in payload
    assert "content" in payload
    assert payload["content"].startswith("# tempo-cli")
