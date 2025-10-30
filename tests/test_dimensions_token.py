import json
from typing import Any, Dict

import pytest

import server_edited as server


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch: pytest.MonkeyPatch):
    """Ensure the module-level cache is clear between tests."""
    server._DIMENSIONS_TOKEN_CACHE["token"] = None
    server._DIMENSIONS_TOKEN_CACHE["expires_at"] = 0.0
    yield
    server._DIMENSIONS_TOKEN_CACHE["token"] = None
    server._DIMENSIONS_TOKEN_CACHE["expires_at"] = 0.0


def test_get_dimensions_token_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIMENSIONS_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        server._get_dimensions_token()

    assert "Dimensions API key is not configured" in str(excinfo.value)


class StubHttpPost:
    def __init__(self) -> None:
        self.calls = 0
        self.payloads: Dict[str, Any] = {}

    def __call__(self, url: str, payload: Any = None, *, headers=None, timeout: int = 10) -> str:
        self.calls += 1
        self.payloads[url] = payload
        return json.dumps({"token": f"token-{self.calls}"})


def test_get_dimensions_token_caches_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIMENSIONS_API_KEY", "secret")
    stub_http = StubHttpPost()

    first = server._get_dimensions_token(http_post=stub_http, time_func=lambda: 0.0)
    second = server._get_dimensions_token(http_post=stub_http, time_func=lambda: 5.0)
    third = server._get_dimensions_token(http_post=stub_http, time_func=lambda: 4000.0)

    assert first == "token-1"
    assert second == "token-1"
    assert third == "token-2"
    assert stub_http.calls == 2
    assert stub_http.payloads[server.DIMENSIONS_AUTH_URL] == {"key": "secret"}


def test_get_dimensions_token_handles_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIMENSIONS_API_KEY", "secret")

    def bad_http_post(*args, **kwargs):
        return "not-json"

    with pytest.raises(RuntimeError) as excinfo:
        server._get_dimensions_token(http_post=bad_http_post)

    assert "invalid JSON" in str(excinfo.value)


def test_get_dimensions_token_wraps_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIMENSIONS_API_KEY", "secret")

    def raising_http_post(*args, **kwargs):
        raise server.DimensionsServiceError(500, "oops")

    with pytest.raises(RuntimeError) as excinfo:
        server._get_dimensions_token(http_post=raising_http_post)

    assert "Dimensions authentication failed" in str(excinfo.value)
