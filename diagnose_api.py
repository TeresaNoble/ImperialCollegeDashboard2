import os
import json
from server_edited import app


def call_dimensions():
    client = app.test_client()
    payload = {"query": "search publications where title contains 'climate'"}
    resp = client.post("/api/dimensions", json=payload)
    print("/api/dimensions ->", resp.status_code)
    try:
        print(json.dumps(resp.get_json(), indent=2))
    except Exception:
        print(resp.get_data(as_text=True))


def call_opportunity():
    client = app.test_client()
    payload = {"term": "climate", "period": "1"}
    resp = client.post("/api/opportunity-predictions", json=payload)
    print("/api/opportunity-predictions ->", resp.status_code)
    try:
        print(json.dumps(resp.get_json(), indent=2))
    except Exception:
        print(resp.get_data(as_text=True))


if __name__ == "__main__":
    print("Environment variables:\n", json.dumps({
        "DIMENSIONS_API_KEY": bool(os.environ.get("DIMENSIONS_API_KEY")),
        "DIMENSIONS_AUTH_URL": os.environ.get("DIMENSIONS_AUTH_URL"),
        "DIMENSIONS_DSL_URL": os.environ.get("DIMENSIONS_DSL_URL")
    }, indent=2))
    print()
    call_opportunity()
    print()
    call_dimensions()
