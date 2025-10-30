from flask import Flask, request, jsonify, send_from_directory
import requests, os

# Create the Flask app FIRST
app = Flask(__name__)

# ✅ Add your Dimensions API key (JWT token) here
DIMENSIONS_API_KEY = "D5D472D56E434D8F93D17B18448424C3"  # replace with your real JWT

login = {
    'key': DIMENSIONS_API_KEY
}
resp = requests.post('https://app.dimensions.ai/api/auth', json=login)
resp.raise_for_status()

@app.route("/api/dimensions", methods=["POST"])
def dimensions_proxy():
    query = request.json.get("query", "")
    print(f"query here: {query}")
    headers = {
        'Authorization': f"JWT {resp.json()['token']}",
        "Content-Type": "application/json"
    }

    res = requests.post(
    'https://app.dimensions.ai/api/dsl/v2', # This is the current major endpoint
    # "https://app.dimensions.ai/api/dsl.json",
    data = query.encode(),
    headers=headers)
    
    print("🔍 Dimensions API status:", res.status_code)
    print("🔍 Response text:", res.text)  # for debugging

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

