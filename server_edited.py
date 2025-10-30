"""Flask application providing helper endpoints for the dashboard.

This module also contains a small Dimensions API client with a cached
authentication token.  The functions are intentionally written so that they
can be exercised directly from the unit tests without requiring a running
Flask server.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from flask import Flask, jsonify, send_from_directory

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = Flask(__name__)


class _RequestShim:
    """Testing-friendly wrapper around :mod:`flask.request`.

    The real :data:`flask.request` object is a context-local proxy which is
    difficult to work with directly inside unit tests.  The shim provides a
    ``set_json`` helper used by the tests while delegating to the real request
    object whenever a request context is active.
    """

    def __init__(self) -> None:
        self._override_json: Optional[Any] = None
        self._has_override = False

    def get_json(self, silent: bool = False) -> Any:  # pragma: no cover - thin wrapper
        if self._has_override:
            return self._override_json

        # Import lazily to avoid circular imports at module load time.
        from flask import request as flask_request  # type: ignore

        try:
            return flask_request.get_json(silent=silent)
        except RuntimeError:
            # Accessing ``flask.request`` without an active request context raises
            # ``RuntimeError``.  In that situation we behave as if no payload was
            # provided.
            return None

    def set_json(self, payload: Any) -> None:
        if payload is None:
            self.clear_json()
            return

        self._override_json = payload
        self._has_override = True

    def clear_json(self) -> None:
        self._override_json = None
        self._has_override = False


request = _RequestShim()


# ---------------------------------------------------------------------------
# Dimensions API helpers
# ---------------------------------------------------------------------------

DIMENSIONS_AUTH_URL = "https://app.dimensions.ai/api/auth"
DIMENSIONS_DSL_URL = "https://app.dimensions.ai/api/dsl/v2"
_DEFAULT_TOKEN_TTL = 3600.0


@dataclass
class DimensionsServiceError(Exception):
    """Error raised when the Dimensions service returns a failure response."""

    status_code: int
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"HTTP {self.status_code}: {self.message}"


_DIMENSIONS_TOKEN_CACHE: Dict[str, Any] = {"token": None, "expires_at": 0.0}


def _http_post(
    url: str,
    payload: Any = None,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 10,
) -> str:
    """Make an HTTP POST request and return the response body as text.

    The function only depends on the Python standard library, which keeps the
    module light-weight for the unit tests while still supporting runtime use in
    the Flask app.
    """

    data: Optional[bytes] = None

    if payload is not None:
        if isinstance(payload, (bytes, bytearray)):
            data = bytes(payload)
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = json.dumps(payload).encode("utf-8")
            headers = {**(headers or {}), "Content-Type": "application/json"}

    req = urllib_request.Request(url, data=data, method="POST")

    for key, value in (headers or {}).items():
        req.add_header(key, value)

    try:
        with urllib_request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return body
    except HTTPError as exc:  # pragma: no cover - network errors are hard to simulate
        raise DimensionsServiceError(exc.code, exc.reason)
    except URLError as exc:  # pragma: no cover - network errors are hard to simulate
        raise RuntimeError(f"Network error contacting Dimensions: {exc.reason}") from exc


def _get_dimensions_token(
    *,
    http_post: Callable[..., str] = _http_post,
    time_func: Callable[[], float] = time.time,
) -> str:
    """Return a cached JWT token for the Dimensions API."""

    cached = _DIMENSIONS_TOKEN_CACHE.get("token")
    expires_at = float(_DIMENSIONS_TOKEN_CACHE.get("expires_at", 0.0))
    if cached and time_func() < expires_at:
        return cached

    api_key = os.environ.get("DIMENSIONS_API_KEY")
    if not api_key:
        raise RuntimeError("Dimensions API key is not configured.")

    try:
        response_text = http_post(
            DIMENSIONS_AUTH_URL,
            {"key": api_key},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
    except DimensionsServiceError as exc:
        raise RuntimeError("Dimensions authentication failed: service error.") from exc

    try:
        response_data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Dimensions authentication failed: invalid JSON response.") from exc

    token = response_data.get("token")
    if not token:
        raise RuntimeError("Dimensions authentication failed: token missing from response.")

    expires_in = float(response_data.get("expires_in", _DEFAULT_TOKEN_TTL))
    _DIMENSIONS_TOKEN_CACHE["token"] = token
    _DIMENSIONS_TOKEN_CACHE["expires_at"] = time_func() + max(0.0, expires_in)

    return token


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/api/dimensions", methods=["POST"])
def dimensions_proxy():
    payload = request.get_json(silent=True) or {}
    query = payload.get("query") if isinstance(payload, dict) else None

    if not query:
        return jsonify({"error": "Missing DSL query payload."}), 400

    try:
        token = _get_dimensions_token()
    except RuntimeError as exc:
        return (
            jsonify(
                {
                    "error": "Unable to authenticate with Dimensions.",
                    "details": str(exc),
                }
            ),
            500,
        )

    headers = {
        "Authorization": f"JWT {token}",
        "Content-Type": "application/json",
    }

    try:
        response_text = _http_post(
            DIMENSIONS_DSL_URL,
            query,
            headers=headers,
            timeout=30,
        )
    except DimensionsServiceError as exc:  # pragma: no cover - see note above
        return (
            jsonify(
                {
                    "error": "Dimensions API request failed.",
                    "status": exc.status_code,
                    "details": exc.message,
                }
            ),
            502,
        )
    except RuntimeError as exc:  # pragma: no cover - network errors are hard to simulate
        return (
            jsonify({"error": "Network error contacting Dimensions.", "details": str(exc)}),
            502,
        )

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON response from Dimensions."}), 502


@app.route("/api/opportunity-predictions", methods=["POST"])
def opportunity_predictions():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}

    term = payload.get("term")
    period = payload.get("period", "3")

    if not term:
        return jsonify({"error": "Missing required field: term"}), 400

    # The predictions are placeholder data used by the dashboard.  In a real
    # implementation these would be calculated using a model; here we return a
    # deterministic stub so the front-end has predictable data to work with.
    predictions = [
        {"year": 2024, "count": 42},
        {"year": 2025, "count": 47},
        {"year": 2026, "count": 53},
    ]

    return {
        "term": term,
        "period": str(period),
        "predictions": predictions,
    }


@app.route("/")
def serve_dashboard():  # pragma: no cover - file serving is trivial
    return send_from_directory(os.getcwd(), "dashboard.html")


if __name__ == "__main__":  # pragma: no cover - manual execution only
    app.run(debug=True)
