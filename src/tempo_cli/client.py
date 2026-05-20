from __future__ import annotations

import email.utils
import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx

from .errors import ConfigError, TempoApiError

DEFAULT_BASE_URL = "https://api.tempo.io/4"
DEFAULT_TIMEOUT = 20.0


def _base_url() -> str:
    return os.environ.get("TEMPO_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
MAX_ATTEMPTS = 3            # total attempts incl. the first; "retries" = MAX_ATTEMPTS - 1
RETRY_BACKOFF_BASE = 0.5    # seconds; doubled per attempt
RETRY_DELAY_CAP = 60.0      # never sleep longer than this in one go


def _parse_retry_after(header_value: str | None, fallback: float) -> float:
    """Parse a Retry-After header (RFC 7231: delta-seconds OR HTTP-date) → seconds.

    Falls back to `fallback` on missing/unparseable values. Clamps to RETRY_DELAY_CAP
    so a hostile or buggy upstream cannot hang us.
    """
    if not header_value:
        return min(max(fallback, 0.0), RETRY_DELAY_CAP)
    try:
        secs = float(header_value)
    except ValueError:
        try:
            target = email.utils.parsedate_to_datetime(header_value)
        except (TypeError, ValueError):
            return min(max(fallback, 0.0), RETRY_DELAY_CAP)
        if target is None:
            return min(max(fallback, 0.0), RETRY_DELAY_CAP)
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        secs = (target - datetime.now(tz=UTC)).total_seconds()
    return min(max(secs, 0.0), RETRY_DELAY_CAP)


def _token() -> str:
    tok = os.environ.get("TEMPO_API_TOKEN")
    if not tok:
        raise ConfigError("TEMPO_API_TOKEN env var is not set")
    return tok


class _BearerAuth(httpx.Auth):
    """Attach `Authorization: Bearer …` per-request. Using httpx's `auth=` slot rather
    than the `headers=` slot makes httpx strip the credential on cross-host redirects.
    """

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


class TempoClient:
    """Thin httpx wrapper over the Tempo v4 REST API."""

    def __init__(self, *, base_url: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self._http = httpx.Client(
            base_url=base_url if base_url is not None else _base_url(),
            auth=_BearerAuth(_token()),
            headers={"Accept": "application/json"},
            timeout=DEFAULT_TIMEOUT,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> TempoClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: Any | None = None,
    ) -> Any:
        last_exc: Exception | None = None
        headers = {"Content-Type": "application/json"} if json is not None else None
        # Network-error retries apply only to idempotent reads — a write that returns
        # mid-flight could have succeeded server-side; re-POST would duplicate.
        retry_on_network_error = method.upper() == "GET"
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = self._http.request(method, path, params=params, json=json, headers=headers)
            except httpx.RequestError as e:
                last_exc = e
                if retry_on_network_error and attempt < MAX_ATTEMPTS - 1:
                    time.sleep(min(RETRY_BACKOFF_BASE * (2**attempt), RETRY_DELAY_CAP))
                    continue
                raise TempoApiError(f"network error: {e}", status=0) from e
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt < MAX_ATTEMPTS - 1:
                    delay = _parse_retry_after(
                        resp.headers.get("Retry-After"),
                        RETRY_BACKOFF_BASE * (2**attempt),
                    )
                    time.sleep(delay)
                    continue
            if not resp.is_success:
                details: Any
                try:
                    details = resp.json()
                except ValueError:
                    details = resp.text
                raise TempoApiError(
                    f"Tempo API {method} {path} → HTTP {resp.status_code}",
                    status=resp.status_code,
                    details=details,
                )
            if resp.status_code == 204 or not resp.content:
                return None
            try:
                return resp.json()
            except ValueError as e:
                raise TempoApiError(
                    f"Tempo returned non-JSON body for {path}", status=resp.status_code
                ) from e
        # Should not reach here
        if last_exc:
            raise TempoApiError(str(last_exc), status=0)
        raise TempoApiError("unreachable", status=0)

    def get(self, path: str, *, params: dict | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, body: Any) -> Any:
        return self.request("POST", path, json=body)

    def put(self, path: str, body: Any) -> Any:
        return self.request("PUT", path, json=body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def paginate(self, path: str, *, params: dict | None = None, page_size: int = 100) -> Iterator[dict]:
        """Yield every result across paginated responses ({results, metadata}).

        Tempo v4 uses limit/offset and exposes metadata.next URLs; we follow `offset`.
        """
        offset = 0
        params = dict(params or {})
        while True:
            params["limit"] = page_size
            params["offset"] = offset
            page = self.request("GET", path, params=params)
            if not isinstance(page, dict):
                return
            results = page.get("results") or []
            yield from results
            if len(results) < page_size:
                return
            offset += page_size
