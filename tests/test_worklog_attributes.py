import pytest

from tempo_cli.commands.worklog import _parse_attributes
from tempo_cli.errors import InputError


def test_parse_attributes_none():
    assert _parse_attributes(None) is None
    assert _parse_attributes([]) is None


def test_parse_attributes_basic():
    assert _parse_attributes(["_Activity_=Dev", "Type=Code"]) == [
        {"key": "_Activity_", "value": "Dev"},
        {"key": "Type", "value": "Code"},
    ]


def test_parse_attributes_empty_value_ok():
    assert _parse_attributes(["Foo="]) == [{"key": "Foo", "value": ""}]


def test_parse_attributes_value_with_equals():
    # Only the first '=' splits — value may itself contain '='
    assert _parse_attributes(["X=a=b=c"]) == [{"key": "X", "value": "a=b=c"}]


@pytest.mark.parametrize("bad", ["no-equals-sign", "=value-only", " ="])
def test_parse_attributes_invalid(bad):
    with pytest.raises(InputError):
        _parse_attributes([bad])
