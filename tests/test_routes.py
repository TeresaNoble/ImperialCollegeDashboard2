import json
from typing import Any

import pytest

import server_edited as server


def _as_body_status(result):
    """Normalise Flask-style return values for assertions."""

    if isinstance(result, tuple):
        body, status = result
        return body, status
    return result, 200


def test_dimensions_proxy_missing_query() -> None:
    server.request.set_json({})  # type: ignore[attr-defined]
    response_body, status = _as_body_status(server.dimensions_proxy())
    server.request.set_json(None)  # type: ignore[attr-defined]
    assert status == 400
    assert response_body["error"] == "Missing DSL query payload."


def test_dimensions_proxy_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIMENSIONS_API_KEY", "secret")
    monkeypatch.setattr(server, "_get_dimensions_token", lambda **kwargs: "cached-token")

    def fake_http_post(url: str, payload: Any = None, *, headers=None, timeout: int = 10) -> str:
        assert headers["Authorization"] == "JWT cached-token"
        assert timeout == 30
        return json.dumps({"results": [1, 2, 3]})

    monkeypatch.setattr(server, "_http_post", fake_http_post)

    server.request.set_json({"query": "search records"})  # type: ignore[attr-defined]
    response, status = _as_body_status(server.dimensions_proxy())
    server.request.set_json(None)  # type: ignore[attr-defined]

    assert status == 200
    assert response == {"results": [1, 2, 3]}


def test_dimensions_proxy_handles_token_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raising_token(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(server, "_get_dimensions_token", raising_token)
    server.request.set_json({"query": "anything"})  # type: ignore[attr-defined]
    response_body, status = _as_body_status(server.dimensions_proxy())
    server.request.set_json(None)  # type: ignore[attr-defined]

    assert status == 500
    assert response_body["error"] == "Unable to authenticate with Dimensions."
    assert response_body["details"] == "boom"


def test_opportunity_predictions_success() -> None:
    server.request.set_json({"term": "AI", "period": "5"})  # type: ignore[attr-defined]
    response, status = _as_body_status(server.opportunity_predictions())
    server.request.set_json(None)  # type: ignore[attr-defined]
    assert status == 200
    assert response["term"] == "AI"
    assert response["period"] == "5"
    assert len(response["predictions"]) == 3


def test_opportunity_predictions_requires_term() -> None:
    server.request.set_json({"period": "5"})  # type: ignore[attr-defined]
    response_body, status = _as_body_status(server.opportunity_predictions())
    server.request.set_json(None)  # type: ignore[attr-defined]
    assert status == 400
    assert response_body["error"] == "Missing required field: term"
