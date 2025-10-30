from flask import Flask, request, jsonify, send_from_directory
import requests
import os
from typing import Optional, Dict, Any

# Create the Flask app FIRST
app = Flask(__name__)

# Cache for the Dimensions token
_dimensions_token: Optional[str] = None

def _get_dimensions_token() -> str:
    """Get a Dimensions API token, using cache if available."""
    global _dimensions_token
    
    if _dimensions_token is not None:
        return _dimensions_token
        
    api_key = os.environ.get('DIMENSIONS_API_KEY')
    if not api_key:
        if os.environ.get("GITHUB_ACTIONS"):
            raise RuntimeError(
                "Dimensions API key not found. Add it as a GitHub secret named 'DIMENSIONS_API_KEY' "
                "and use it in your workflow with: env: DIMENSIONS_API_KEY: ${{ secrets.DIMENSIONS_API_KEY }}"
            )
        raise RuntimeError("Dimensions API key not configured. Set DIMENSIONS_API_KEY environment variable.")
    
    try:
        resp = requests.post(
            'https://app.dimensions.ai/api/auth',
            json={'key': api_key},
            timeout=10
        )
        resp.raise_for_status()
        token = resp.json().get('token')
        if not token:
            raise RuntimeError("No token in Dimensions response")
        _dimensions_token = token
        return token
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to authenticate with Dimensions: {str(e)}") from e

@app.route("/api/dimensions", methods=["POST"])
def dimensions_proxy():
    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify({"error": "Missing request body"}), 400
            
        query = payload.get("query", "")
        if not query:
            return jsonify({"error": "Missing query parameter"}), 400
            
        print(f"Query: {query}")
        
        try:
            # Get fresh token (or use cached one)
            token = _get_dimensions_token()
            
            headers = {
                'Authorization': f"JWT {token}",
                'Content-Type': 'application/json'
            }

            res = requests.post(
                'https://app.dimensions.ai/api/dsl/v2',
                data=query.encode(),
                headers=headers,
                timeout=30
            )
            
            print("🔍 Dimensions API status:", res.status_code)
            res.raise_for_status()
            
            try:
                return jsonify(res.json())
            except ValueError:
                return jsonify({
                    "error": "Invalid JSON response from Dimensions",
                    "details": res.text
                }), 502
                
        except requests.exceptions.RequestException as e:
            return jsonify({
                "error": "Dimensions DSL request failed",
                "details": str(e)
            }), 502
            
    except RuntimeError as e:
        return jsonify({
            "error": "Dimensions authentication failed",
            "details": str(e)
        }), 500
    except Exception as e:
        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500

    try:
        return jsonify(res.json())
    except Exception:
        return jsonify({"error": "Invalid JSON response from Dimensions",
                        "status": res.status_code})
@app.route('/')
def serve_dashboard():
    return send_from_directory(os.getcwd(), 'dashboard.html')

if __name__ == "__main__":
    app.run(debug=True)

