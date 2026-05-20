
import httpx
import pytest

from tempo_cli.client import TempoClient
from tempo_cli.errors import ConfigError, TempoApiError


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("TEMPO_API_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        TempoClient()


def test_paginate_walks_offsets(fake_token):
    pages = {
        0: [{"id": i} for i in range(100)],
        100: [{"id": i} for i in range(100, 130)],
    }

    def handler(req: httpx.Request) -> httpx.Response:
        offset = int(req.url.params.get("offset", "0"))
        body = {"results": pages.get(offset, [])}
        return httpx.Response(200, json=body)

    client = TempoClient(transport=httpx.MockTransport(handler))
    results = list(client.paginate("/worklogs/user/X"))
    assert len(results) == 130
    assert results[0]["id"] == 0
    assert results[-1]["id"] == 129
    client.close()


def test_error_body_propagates(fake_token):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errors": [{"message": "bad"}]})

    client = TempoClient(transport=httpx.MockTransport(handler))
    with pytest.raises(TempoApiError) as exc:
        client.get("/worklogs/user/X")
    assert exc.value.status == 400
    assert "errors" in (exc.value.details or {})
    client.close()


def test_204_returns_none(fake_token):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = TempoClient(transport=httpx.MockTransport(handler))
    assert client.delete("/worklogs/1") is None
    client.close()
