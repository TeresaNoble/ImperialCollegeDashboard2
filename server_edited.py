import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from flask import Flask, jsonify, request, send_from_directory  # type: ignore

# Create the Flask app FIRST
app = Flask(__name__)


DIMENSIONS_AUTH_URL = os.environ.get("DIMENSIONS_AUTH_URL", "https://app.dimensions.ai/api/auth")
DIMENSIONS_DSL_URL = os.environ.get("DIMENSIONS_DSL_URL", "https://app.dimensions.ai/api/dsl/v2")
_DIMENSIONS_TOKEN_CACHE: Dict[str, Optional[Any]] = {"token": None, "expires_at": 0.0}


class DimensionsServiceError(RuntimeError):
    """Exception raised when the Dimensions API responds with an HTTP error."""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


def _http_post(url: str, payload: Any = None, *, headers: Optional[Dict[str, str]] = None,
               timeout: int = 10) -> str:
    """Minimal HTTP POST helper using urllib to avoid third-party dependencies."""

    data: Optional[bytes]
    req_headers: Dict[str, str] = {}

    if isinstance(payload, (dict, list)):
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    elif isinstance(payload, str):
        data = payload.encode("utf-8")
    elif payload is None:
        data = None
    elif isinstance(payload, (bytes, bytearray)):
        data = bytes(payload)
    else:
        raise TypeError("Unsupported payload type for _http_post")

    if headers:
        req_headers.update(headers)

    request_obj = urllib_request.Request(url, data=data, headers=req_headers, method="POST")

    try:
        with urllib_request.urlopen(request_obj, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, "replace")
    except urllib_error.HTTPError as exc:
        body = exc.read().decode(exc.headers.get_content_charset() or "utf-8", "replace")
        raise DimensionsServiceError(exc.code, body) from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Network error contacting {url}: {exc.reason}") from exc


def _get_dimensions_token(*, http_post=_http_post, time_func=time.time) -> str:
    """Return a cached Dimensions token, refreshing it when expired.

    The previous implementation authenticated at import time with a hard-coded
    key, which is brittle for deployments and also risked committing secrets to
    source control. We now read the API key from the ``DIMENSIONS_API_KEY``
    environment variable and lazily authenticate when the proxy endpoint is
    called. Tokens are cached for 50 minutes (Dimensions issues one-hour tokens)
    to avoid re-authenticating on every request. ``http_post`` and
    ``time_func`` are injectable to keep the helper easy to unit test while
    defaulting to the production implementations.
    """

    api_key = os.environ.get("DIMENSIONS_API_KEY")
    if not api_key:
        raise RuntimeError("Dimensions API key is not configured. Set DIMENSIONS_API_KEY.")

    token = _DIMENSIONS_TOKEN_CACHE.get("token")
    expires_at = float(_DIMENSIONS_TOKEN_CACHE.get("expires_at") or 0.0)
    if token and time_func() < expires_at:
        return str(token)

    try:
        response_text = http_post(DIMENSIONS_AUTH_URL, {"key": api_key}, timeout=10)
    except DimensionsServiceError as exc:  # pragma: no cover - network behaviour
        raise RuntimeError(
            f"Dimensions authentication failed with status {exc.status}: {exc.body}"
        ) from exc
    try:
        token = json.loads(response_text).get("token")
    except json.JSONDecodeError as exc:  # pragma: no cover - invalid upstream response
        raise RuntimeError("Dimensions authentication returned invalid JSON.") from exc
    if not token:
        raise RuntimeError("Dimensions authentication response did not include a token.")

    _DIMENSIONS_TOKEN_CACHE["token"] = token
    _DIMENSIONS_TOKEN_CACHE["expires_at"] = time_func() + (50 * 60)  # 50 minutes
    return token


def _generate_mock_predictions(term: str, period: str) -> Dict[str, Any]:
    """Return deterministic mock predictions for opportunity scouting.

    This keeps the dashboard functional while the production AI service is
    being finalised. To wire up the real model once available, replace the
    body of this helper with an HTTPS request to the Imperial-hosted service
    (for example, using ``requests.post`` against the API Gateway URL) and
    forward the authentication headers required by ICT. Keep the return
    structure identical so the front-end continues to work unchanged.
    """

    base_confidence = 0.82
    period_hint = {
        "all": "Stable funding outlook",
        "1": "Emerging call volume",
        "5": "Sustained growth trajectory"
    }.get(period, "Mixed opportunity signals")

    challenges: List[Dict[str, Any]] = [
        {
            "rank": 1,
            "challenge": f"Transdisciplinary {term} demonstrator programme",
            "confidence": round(base_confidence + 0.08, 2),
            "supporting_metrics": {
                "publication_gap": "Imperial publications down 15% vs. global peers",
                "funding_trend": f"{period_hint} (+11% YoY awards)",
                "policy_momentum": "Highlighted in UKRI 2030 roadmap"
            },
            "recommended_collaborators": [
                {
                    "name": "Centre for Climate Finance",
                    "profile_url": "https://www.imperial.ac.uk/climate-finance"
                },
                {
                    "name": "Institute for Security Science and Technology",
                    "profile_url": "https://www.imperial.ac.uk/isst"
                }
            ]
        },
        {
            "rank": 2,
            "challenge": f"Industry partnership on scalable {term} analytics",
            "confidence": round(base_confidence, 2),
            "supporting_metrics": {
                "publication_gap": "High citation growth but limited UK leads",
                "funding_trend": "£24m pipeline identified across Innovate UK",
                "talent_indicator": "42 active Imperial PIs in adjacent areas"
            },
            "recommended_collaborators": [
                {
                    "name": "Data Science Institute",
                    "profile_url": "https://www.imperial.ac.uk/data-science"
                },
                {
                    "name": "Corporate Partnerships Team",
                    "profile_url": "https://www.imperial.ac.uk/enterprise/partners"
                }
            ]
        },
        {
            "rank": 3,
            "challenge": f"Pan-European {term} resilience consortium",
            "confidence": round(base_confidence - 0.05, 2),
            "supporting_metrics": {
                "publication_gap": "EU programmes request UK leadership",
                "funding_trend": "€18m Horizon Europe calls opening Q4",
                "collaboration_index": "Imperial co-authorship network density at 0.61"
            },
            "recommended_collaborators": [
                {
                    "name": "Grantham Institute",
                    "profile_url": "https://www.imperial.ac.uk/grantham"
                },
                {
                    "name": "Imperial Enterprise Lab",
                    "profile_url": "https://www.imperial.ac.uk/enterpriselab"
                }
            ]
        }
    ]

    return {
        "term": term,
        "period": period,
        "predictions": challenges
    }


@app.route("/api/dimensions", methods=["POST"])
def dimensions_proxy():
    payload = request.get_json(force=True) or {}
    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Missing DSL query payload."}), 400

    try:
        token = _get_dimensions_token()
    except Exception as exc:  # pragma: no cover - surfaced via JSON response
        return jsonify({
            "error": "Unable to authenticate with Dimensions.",
            "details": str(exc)
        }), 500

    try:
        response_text = _http_post(
            DIMENSIONS_DSL_URL,
            query,
            headers={
                "Authorization": f"JWT {token}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
    except DimensionsServiceError as exc:  # pragma: no cover - network behaviour
        return jsonify({
            "error": "Dimensions DSL request failed.",
            "details": exc.body
        }), exc.status
    except RuntimeError as exc:  # pragma: no cover - network behaviour
        return jsonify({
            "error": "Dimensions DSL request failed.",
            "details": str(exc)
        }), 502

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return jsonify({
            "error": "Invalid JSON response from Dimensions"
        }), 502

    return jsonify(payload)


@app.route("/api/opportunity-predictions", methods=["POST"])
def opportunity_predictions():
    payload = request.get_json(force=True) or {}
    term = (payload.get("term") or "").strip()
    period = str(payload.get("period") or "all").strip() or "all"

    if not term:
        return jsonify({
            "error": "Missing required field: term"
        }), 400

    # When the production AI model is ready, replace the call below with a
    # requests.post call to the Imperial AI microservice, for example:
    #
    #   response = requests.post(
    #       os.environ["AI_SERVICE_URL"],
    #       json={"term": term, "period": period},
    #       headers={"Authorization": f"Bearer {token}"},
    #       timeout=15,
    #   )
    #   response.raise_for_status()
    #   return jsonify(response.json())
    #
    # Storing the base URL and credentials (OAuth client secrets, API keys,
    # etc.) in environment variables keeps the dashboard deployable across
    # Imperial environments. The front end expects the structure returned by
    # ``_generate_mock_predictions`` so the live service should mirror it.
    mock_payload = _generate_mock_predictions(term, period)
    return jsonify(mock_payload)


@app.route('/')
def serve_dashboard():
    return send_from_directory(os.getcwd(), 'dashboard.html')

if __name__ == "__main__":
    # Allow runtime override of host/port via environment variables. This
    # prevents the default Flask port 5000 from being used unexpectedly.
    host = os.environ.get("HOST", "127.0.0.1")
    # Respect FLASK_RUN_PORT (used by flask CLI) or PORT (common in containers).
    # Default to 7000 here to avoid colliding with an already-used 5000.
    port = int(os.environ.get("FLASK_RUN_PORT") or os.environ.get("PORT") or 6000)
    debug = os.environ.get("FLASK_DEBUG", "1").lower() not in ("0", "false", "no")
    app.run(host=host, port=port, debug=debug)

