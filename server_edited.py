from flask import Flask, request, jsonify, send_from_directory
import requests, os
import time

# Create the Flask app
app = Flask(__name__)

# --- 1. SECURE CONFIGURATION ---
# Access the API key from the Codespaces Environment Variable
DIMENSIONS_API_KEY = os.environ.get("DIMENSIONS_API_KEY") 
if not DIMENSIONS_API_KEY:
    # IMPORTANT: Ensure your Codespaces Secret is named "DIMENSIONS_API_KEY"
    raise ValueError("FATAL ERROR: DIMENSIONS_API_KEY environment variable not set or found!")

# --- 2. GLOBAL STATE for Token Management ---
# Use global state to cache the token and its expiry time
token_data = {'token': None, 'expiry_time': 0}
AUTH_URL = 'https://app.dimensions.ai/api/auth'
DSL_URL = 'https://app.dimensions.ai/api/dsl/v2'

def get_fresh_token():
    """Checks if the current token is valid; if not, fetches a new one."""
    # Give a 5-minute buffer (300 seconds) before expiration
    if token_data['token'] and token_data['expiry_time'] > time.time() + 300:
        return token_data['token']

    print("🔑 Token expired or missing. Requesting new token...")
    try:
        login = {'key': DIMENSIONS_API_KEY}
        resp = requests.post(AUTH_URL, json=login)
        resp.raise_for_status()
        
        data = resp.json()
        new_token = data['token']
        # Dimensions tokens usually last 1 hour (3600 seconds)
        token_data['token'] = new_token
        token_data['expiry_time'] = time.time() + 3600 
        print("✅ New token secured.")
        return new_token
    except Exception as e:
        print(f"❌ Failed to get new token: {e}")
        return None 

@app.route("/api/dimensions", methods=["POST"])
def dimensions_proxy():
    query = request.json.get("query", "")
    jwt_token = get_fresh_token() # Ensures the token is always fresh
    
    if not jwt_token:
        # If token acquisition fails, return a 500 error
        return jsonify({"error": "Failed to authenticate with Dimensions API."}), 500

    headers = {
        'Authorization': f"JWT {jwt_token}",
        "Content-Type": "application/json"
    }

    res = requests.post(DSL_URL, data=query.encode(), headers=headers)
    
    print("🔍 Dimensions API status:", res.status_code)

    try:
        # Check for non-200 status codes even if JSON is returned
        if res.status_code != 200:
             return jsonify({"error": f"Dimensions API Error: {res.status_code}",
                        "details": res.json().get('error', res.text[:100])}), res.status_code
        return jsonify(res.json())
    except requests.exceptions.JSONDecodeError:
        # Handle cases where Dimensions returns a non-JSON error (e.g., HTML error page)
        return jsonify({"error": "Invalid or unexpected non-JSON response from Dimensions",
                        "status": res.status_code,
                        "details": res.text[:100]}), 502
    except Exception as e:
        return jsonify({"error": f"An unknown error occurred on the server: {e}"}), 500

@app.route('/')
def serve_dashboard():
    # Serves dashboard.html from the current directory
    return send_from_directory(os.getcwd(), 'dashboard.html')

if __name__ == "__main__":
    # Ensure this script is run in an environment where DIMENSIONS_API_KEY is set
    app.run(debug=True)