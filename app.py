import os
import jwt
import datetime
from functools import wraps
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from sklearn.cluster import KMeans

app = Flask(__name__, static_folder='static')
CORS(app)

JWT_SECRET = "abc123"

USERS = {
    "admin": "password123"
}

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid token"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

TOTP_CODE = "123456"

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    if USERS.get(username) != password:
        return jsonify({"error": "Invalid credentials"}), 401
    temp_token = jwt.encode(
        {
            "sub": username,
            "type": "2fa_pending",
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
        },
        JWT_SECRET,
        algorithm="HS256"
    )
    return jsonify({"requires_2fa": True, "temp_token": temp_token})

@app.route('/api/verify-2fa', methods=['POST'])
def verify_2fa():
    data = request.get_json(silent=True) or {}
    temp_token = data.get("temp_token", "")
    code = data.get("code", "")
    try:
        payload = jwt.decode(temp_token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Session expired, please log in again"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    if payload.get("type") != "2fa_pending":
        return jsonify({"error": "Invalid token"}), 401
    if code != TOTP_CODE:
        return jsonify({"error": "Invalid 2FA code"}), 401
    token = jwt.encode(
        {
            "sub": payload["sub"],
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        },
        JWT_SECRET,
        algorithm="HS256"
    )
    return jsonify({"token": token})

DATA_SOURCE = "https://dietanalysiscpsy.blob.core.windows.net/datasets/All_Diets.csv"

_df_cache = None

def load_data():
    global _df_cache
    if _df_cache is None:
        try:
            print("Downloading data from Blob Storage...")
            df = pd.read_csv(DATA_SOURCE)
            df.fillna(df.mean(numeric_only=True), inplace=True)
            _df_cache = df
        except Exception as e:
            print(f"Data load failed: {e}")
            return pd.DataFrame()
    return _df_cache.copy()

@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'index.html')

@app.route('/api/insights', methods=['GET'])
@token_required
def get_insights():
    df = load_data()
    diet = request.args.get('diet')
    if diet and diet.lower() != "all":
        df = df[df['Diet_type'].str.lower() == diet.lower()]
    
    if df.empty: return jsonify([])
    
    avg_macros = df.groupby("Diet_type")[["Protein(g)", "Carbs(g)", "Fat(g)"]].mean().reset_index()
    return jsonify(avg_macros.to_dict(orient='records'))

@app.route('/api/recipes', methods=['GET'])
@token_required
def get_recipes():
    df = load_data()
    diet = request.args.get('diet')
    if diet and diet.lower() != "all":
        df = df[df['Diet_type'].str.lower() == diet.lower()]
    
    if df.empty: return jsonify([])
    
    num_samples = min(len(df), 50)    
    return jsonify(df.sample(num_samples, random_state=42).to_dict(orient='records'))

@app.route('/api/clusters', methods=['GET'])
@token_required
def get_clusters():
    df = load_data()
    diet = request.args.get('diet')
    if diet and diet.lower() != "all":
        df = df[df['Diet_type'].str.lower() == diet.lower()]

    if df.empty: return jsonify([])

    km = KMeans(n_clusters=3, random_state=42, n_init='auto')
    df['cluster'] = km.fit_predict(df[["Protein(g)", "Carbs(g)", "Fat(g)"]])
    
    num_samples = min(len(df), 50) 
    return jsonify(df[['Recipe_name','Diet_type','cluster']].sample(num_samples, random_state=42).to_dict(orient='records'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)