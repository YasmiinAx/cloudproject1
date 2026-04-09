import os
import jwt
import random
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

# ---------------------------------------------------------------------------
# Data Source
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'index.html')

# ---------------------------------------------------------------------------
# Data API Endpoints (Person 2 — protected with JWT)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Cleanup & Cost Optimization Endpoints (Person 3)
# ---------------------------------------------------------------------------

# Cloud resource inventory based on actual Azure deployment
CLOUD_RESOURCES = [
    {
        "resource_name": "nutritionalinsightscr",
        "resource_type": "Microsoft.ContainerRegistry/registries",
        "location": "canadacentral",
        "sku": "Basic",
        "monthly_cost_cad": 6.87,
        "status": "active",
        "description": "Azure Container Registry — stores Docker images"
    },
    {
        "resource_name": "nutritional-insights-plan",
        "resource_type": "Microsoft.Web/serverFarms",
        "location": "canadacentral",
        "sku": "B1",
        "monthly_cost_cad": 17.52,
        "status": "active",
        "description": "App Service Plan — hosts the web application"
    },
    {
        "resource_name": "nutritional-insights-app",
        "resource_type": "Microsoft.Web/sites",
        "location": "canadacentral",
        "sku": "B1",
        "monthly_cost_cad": 0.00,
        "status": "active",
        "description": "Web App — runs the Docker container (cost included in plan)"
    },
    {
        "resource_name": "nutritionalinsightscr/appserviceCD",
        "resource_type": "Microsoft.ContainerRegistry/registries/webhooks",
        "location": "canadacentral",
        "sku": "N/A",
        "monthly_cost_cad": 0.00,
        "status": "active",
        "description": "ACR Webhook — triggers auto-deployment on image push"
    },
    {
        "resource_name": "dietanalysiscpsy",
        "resource_type": "Microsoft.Storage/storageAccounts",
        "location": "canadacentral",
        "sku": "Standard",
        "monthly_cost_cad": 2.76,
        "status": "active",
        "description": "Blob Storage — hosts the All_Diets.csv dataset"
    }
]

# Stale/unused resources that could be cleaned up
STALE_RESOURCES = [
    {
        "resource_name": "nutritionalinsightscr/nutritional-insights:old-build-abc123",
        "resource_type": "Container Image (stale)",
        "reason": "Old image tag — superseded by latest deployment",
        "estimated_size_mb": 312,
        "savings_cad": 0.04
    },
    {
        "resource_name": "nutritionalinsightscr/nutritional-insights:old-build-def456",
        "resource_type": "Container Image (stale)",
        "reason": "Old image tag — superseded by latest deployment",
        "estimated_size_mb": 310,
        "savings_cad": 0.04
    },
    {
        "resource_name": "nutritionalinsightscr/nutritional-insights:old-build-ghi789",
        "resource_type": "Container Image (stale)",
        "reason": "Old image tag — superseded by latest deployment",
        "estimated_size_mb": 315,
        "savings_cad": 0.04
    },
    {
        "resource_name": "app-service-logs-2025-01",
        "resource_type": "Diagnostic Logs (expired)",
        "reason": "Log data older than 30 days — no longer needed for debugging",
        "estimated_size_mb": 45,
        "savings_cad": 0.01
    },
    {
        "resource_name": "app-service-logs-2025-02",
        "resource_type": "Diagnostic Logs (expired)",
        "reason": "Log data older than 30 days — no longer needed for debugging",
        "estimated_size_mb": 52,
        "savings_cad": 0.01
    },
    {
        "resource_name": "deployment-cache-stale",
        "resource_type": "Deployment Cache",
        "reason": "Cached deployment artifacts from previous CI/CD runs",
        "estimated_size_mb": 128,
        "savings_cad": 0.02
    }
]


@app.route('/api/cleanup', methods=['POST'])
@token_required
def cleanup_resources():
    """
    Simulates a cloud resource cleanup operation.
    
    Accepts optional JSON body:
    {
        "dry_run": true/false  (default: true)
    }
    
    - dry_run=true:  Scans for stale resources, reports what WOULD be cleaned
    - dry_run=false: Simulates actually cleaning up the resources
    """
    data = request.get_json(silent=True) or {}
    dry_run = data.get("dry_run", True)

    total_monthly_cost = sum(r["monthly_cost_cad"] for r in CLOUD_RESOURCES)
    active_resources = [r for r in CLOUD_RESOURCES if r["status"] == "active"]

    resources_to_clean = STALE_RESOURCES.copy()
    total_size_freed_mb = sum(r["estimated_size_mb"] for r in resources_to_clean)
    total_savings = sum(r["savings_cad"] for r in resources_to_clean)

    cleanup_actions = []
    for resource in resources_to_clean:
        cleanup_actions.append({
            "resource": resource["resource_name"],
            "type": resource["resource_type"],
            "reason": resource["reason"],
            "size_mb": resource["estimated_size_mb"],
            "monthly_savings_cad": resource["savings_cad"],
            "status": "would_delete" if dry_run else "deleted"
        })

    recommendations = [
        {
            "recommendation": "Scale down App Service Plan during off-hours",
            "current_sku": "B1",
            "suggested_sku": "F1 (Free) for dev/test",
            "potential_savings_cad": 17.52,
            "priority": "high"
        },
        {
            "recommendation": "Enable ACR retention policy to auto-delete old images",
            "details": "Keep only the 5 most recent image tags",
            "potential_savings_cad": 0.50,
            "priority": "medium"
        },
        {
            "recommendation": "Set up blob storage lifecycle management",
            "details": "Move infrequently accessed data to cool storage tier",
            "potential_savings_cad": 1.38,
            "priority": "low"
        }
    ]

    response = {
        "cleanup_report": {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "mode": "dry_run" if dry_run else "executed",
            "resource_group": "nutritional-insights-rg",
            "region": "canadacentral"
        },
        "active_resources": {
            "count": len(active_resources),
            "total_monthly_cost_cad": round(total_monthly_cost, 2),
            "resources": [
                {
                    "name": r["resource_name"],
                    "type": r["resource_type"],
                    "monthly_cost_cad": r["monthly_cost_cad"],
                    "description": r["description"]
                }
                for r in active_resources
            ]
        },
        "cleanup_actions": {
            "items_found": len(cleanup_actions),
            "total_size_freed_mb": total_size_freed_mb,
            "total_monthly_savings_cad": round(total_savings, 2),
            "actions": cleanup_actions
        },
        "cost_recommendations": recommendations,
        "summary": {
            "current_monthly_cost_cad": round(total_monthly_cost, 2),
            "potential_monthly_savings_cad": round(
                total_savings + sum(r["potential_savings_cad"] for r in recommendations), 2
            ),
            "optimized_monthly_cost_cad": round(
                total_monthly_cost - total_savings - sum(r["potential_savings_cad"] for r in recommendations), 2
            )
        }
    }

    return jsonify(response)


@app.route('/api/cleanup/status', methods=['GET'])
@token_required
def cleanup_status():
    """
    Returns the current resource inventory and cost summary.
    No cleanup is performed — read-only status check.
    """
    total_monthly_cost = sum(r["monthly_cost_cad"] for r in CLOUD_RESOURCES)

    return jsonify({
        "resource_group": "nutritional-insights-rg",
        "region": "canadacentral",
        "subscription": "Azure for Students",
        "total_resources": len(CLOUD_RESOURCES),
        "total_monthly_cost_cad": round(total_monthly_cost, 2),
        "resources": CLOUD_RESOURCES,
        "stale_items_detected": len(STALE_RESOURCES),
        "cleanup_available": True
    })


# ---------------------------------------------------------------------------
# Server Startup
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
