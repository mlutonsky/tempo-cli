import json

import pytest

from tempo_cli.errors import TempoApiError
from tempo_cli.output import emit_error, emit_json


def test_emit_json(capsys):
    emit_json({"a": 1, "b": [2, 3]})
    out, err = capsys.readouterr()
    assert json.loads(out) == {"a": 1, "b": [2, 3]}
    assert err == ""


def test_emit_error_structured(capsys):
    with pytest.raises(SystemExit) as exc:
        emit_error(TempoApiError("nope", status=401, details={"x": 1}))
    out, err = capsys.readouterr()
    payload = json.loads(err)
    assert payload["error"]["code"] == "tempo_api_error"
    assert payload["error"]["status"] == 401
    assert payload["error"]["details"] == {"x": 1}
    assert exc.value.code == 1


def test_emit_error_generic_exception(capsys):
    with pytest.raises(SystemExit):
        emit_error(RuntimeError("boom"))
    out, err = capsys.readouterr()
    payload = json.loads(err)
    assert payload["error"]["code"] == "internal_error"
    assert payload["error"]["message"] == "boom"
