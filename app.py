import os
import jwt
import json
import datetime
import urllib.request
import urllib.error
import base64
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

def get_username_from_token():
    """Extract username from the JWT token for audit logging."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            return payload.get("sub", "unknown")
        except Exception:
            pass
    return "unknown"

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
# Cleanup & Cost Optimization System (Person 3)
# ---------------------------------------------------------------------------
# 
# Two-step cleanup flow (best practice):
#   1. GET  /api/cleanup/status  → scan and show what CAN be cleaned
#   2. POST /api/cleanup         → requires {"confirm": true} to actually delete
#
# Safeguards:
#   - Never deletes the "latest" tag (that's the running app)
#   - Requires explicit confirmation in the request body
#   - Logs who initiated the cleanup (from JWT)
#   - Returns detailed results for every action taken
# ---------------------------------------------------------------------------

# Active cloud resources — these are PROTECTED and never touched by cleanup
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

# ACR configuration (injected by Azure App Service as env vars)
ACR_REGISTRY = os.environ.get("DOCKER_REGISTRY_SERVER_URL", "https://nutritionalinsightscr.azurecr.io").rstrip("/")
ACR_USERNAME = os.environ.get("DOCKER_REGISTRY_SERVER_USERNAME", "nutritionalinsightscr")
ACR_PASSWORD = os.environ.get("ACR_CLEANUP_PASSWORD", os.environ.get("DOCKER_REGISTRY_SERVER_PASSWORD", ""))
ACR_IMAGE_NAME = "nutritional-insights"

# Tags that must NEVER be deleted
PROTECTED_TAGS = {"latest"}

# Cleanup audit log (in-memory for this deployment)
cleanup_log = []


def _acr_request(path, method="GET", headers=None):
    """Make an authenticated request to the ACR REST API."""
    url = f"{ACR_REGISTRY}{path}"
    credentials = base64.b64encode(f"{ACR_USERNAME}:{ACR_PASSWORD}".encode()).decode()
    req_headers = {"Authorization": f"Basic {credentials}"}
    if headers:
        req_headers.update(headers)
    
    req = urllib.request.Request(url, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            return {
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": json.loads(body) if body else {}
            }
    except urllib.error.HTTPError as e:
        return {"status": e.code, "headers": {}, "body": {}}
    except Exception as e:
        return {"status": 0, "headers": {}, "body": {}, "error": str(e)}


def get_acr_tags():
    """Fetch all image tags from Azure Container Registry."""
    result = _acr_request(f"/v2/{ACR_IMAGE_NAME}/tags/list")
    if result["status"] == 200:
        return result["body"].get("tags", [])
    return []


def delete_acr_image(tag):
    """Delete a specific image tag from ACR by its manifest digest."""
    # Step 1: Get the manifest digest for this tag
    result = _acr_request(
        f"/v2/{ACR_IMAGE_NAME}/manifests/{tag}",
        headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
    )
    if result["status"] != 200:
        return {"tag": tag, "status": "failed", "reason": f"Could not fetch manifest (HTTP {result['status']})"}

    digest = result["headers"].get("Docker-Content-Digest") or result["headers"].get("docker-content-digest")
    if not digest:
        return {"tag": tag, "status": "failed", "reason": "No digest found in manifest response"}

    # Step 2: Delete the manifest by digest
    del_result = _acr_request(f"/v2/{ACR_IMAGE_NAME}/manifests/{digest}", method="DELETE")
    if del_result["status"] in (200, 202, 204):
        return {"tag": tag, "status": "deleted", "digest": digest[:20] + "..."}
    else:
        return {"tag": tag, "status": "failed", "reason": f"Delete returned HTTP {del_result['status']}"}


# Unused project files that bloat the Docker image
UNUSED_PROJECT_FILES = [
    {
        "file": "lambda_function.py",
        "type": "Serverless Function (unused)",
        "reason": "Project 1 Lambda function — replaced by Flask API in Project 2",
        "size_kb": 1,
        "recommendation": "Remove from repo or add to .dockerignore"
    },
    {
        "file": "avg_protein.png, avg_carbs_fat.png, macro_heatmap.png, top_protein_scatter.png",
        "type": "Static Chart Images (unused)",
        "reason": "Project 1 chart outputs — charts now rendered dynamically in frontend via Chart.js",
        "size_kb": 120,
        "recommendation": "Remove from repo or add to .dockerignore"
    },
    {
        "file": "azurite_data/",
        "type": "Local Storage Simulation (unused)",
        "reason": "Azurite emulator data from Project 1 — replaced by real Azure Blob Storage",
        "size_kb": 50,
        "recommendation": "Remove from repo or add to .dockerignore"
    },
    {
        "file": "simulated_nosql/",
        "type": "Local NoSQL Simulation (unused)",
        "reason": "Simulated NoSQL files from Project 1 — no longer used in Project 2/3",
        "size_kb": 30,
        "recommendation": "Remove from repo or add to .dockerignore"
    },
    {
        "file": "All_Diets.csv",
        "type": "Dataset File (redundant in Docker image)",
        "reason": "700KB CSV copied into every Docker build — app reads from Azure Blob Storage now",
        "size_kb": 700,
        "recommendation": "Add to .dockerignore to reduce image size"
    }
]


@app.route('/api/cleanup/status', methods=['GET'])
@token_required
def cleanup_status():
    """
    Step 1 of cleanup flow: Scan and report.
    
    Returns:
    - Active resources (protected, won't be touched)
    - Stale Docker image tags in ACR (candidates for deletion)
    - Unused project files bloating the Docker image
    - Cost optimization recommendations
    """
    total_monthly_cost = sum(r["monthly_cost_cad"] for r in CLOUD_RESOURCES)
    
    # Scan ACR for image tags
    all_tags = get_acr_tags()
    stale_tags = [t for t in all_tags if t not in PROTECTED_TAGS]
    estimated_storage_mb = len(stale_tags) * 150  # ~150MB per image

    return jsonify({
        "scan_timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "resource_group": "nutritional-insights-rg",
        "region": "canadacentral",
        "active_resources": {
            "count": len(CLOUD_RESOURCES),
            "total_monthly_cost_cad": round(total_monthly_cost, 2),
            "note": "These resources are PROTECTED and will not be affected by cleanup",
            "resources": CLOUD_RESOURCES
        },
        "stale_acr_images": {
            "total_tags_in_registry": len(all_tags),
            "protected_tags": list(PROTECTED_TAGS),
            "stale_tags_found": len(stale_tags),
            "stale_tag_list": stale_tags,
            "estimated_storage_mb": estimated_storage_mb,
            "estimated_monthly_cost_cad": round(len(stale_tags) * 0.014, 2)
        },
        "unused_project_files": {
            "items": UNUSED_PROJECT_FILES,
            "total_wasted_size_kb": sum(f["size_kb"] for f in UNUSED_PROJECT_FILES)
        },
        "cost_recommendations": [
            {
                "recommendation": "Scale down App Service Plan during off-hours",
                "current_sku": "B1",
                "suggested_sku": "F1 (Free) for dev/test",
                "potential_savings_cad": 17.52,
                "priority": "high"
            },
            {
                "recommendation": "Enable ACR retention policy to auto-purge old images",
                "details": "Prevents stale image buildup automatically",
                "potential_savings_cad": 0.50,
                "priority": "medium"
            },
            {
                "recommendation": "Add .dockerignore to exclude unused files from builds",
                "details": "Exclude PNGs, azurite_data/, simulated_nosql/, All_Diets.csv",
                "potential_savings_cad": 0.00,
                "priority": "medium",
                "benefit": "Faster builds, smaller images, less ACR storage"
            },
            {
                "recommendation": "Set up blob storage lifecycle management",
                "details": "Move infrequently accessed data to cool storage tier",
                "potential_savings_cad": 1.38,
                "priority": "low"
            }
        ],
        "cleanup_available": len(stale_tags) > 0,
        "next_step": "POST /api/cleanup with {\"confirm\": true} to delete stale images"
    })


@app.route('/api/cleanup', methods=['POST'])
@token_required
def cleanup_resources():
    """
    Step 2 of cleanup flow: Execute cleanup.
    
    Requires: {"confirm": true} in the request body.
    Without confirmation, returns a preview of what would be deleted.
    
    Actions:
    - Deletes stale Docker image tags from ACR (keeps 'latest')
    - Logs the cleanup action with timestamp and user
    - Returns detailed results for every deletion
    """
    data = request.get_json(silent=True) or {}
    confirmed = data.get("confirm", False)
    initiated_by = get_username_from_token()
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"

    total_monthly_cost = sum(r["monthly_cost_cad"] for r in CLOUD_RESOURCES)

    # Scan ACR for stale tags
    all_tags = get_acr_tags()
    stale_tags = [t for t in all_tags if t not in PROTECTED_TAGS]

    # ── If not confirmed: return preview ──────────────────────────────────
    if not confirmed:
        return jsonify({
            "status": "confirmation_required",
            "message": "Cleanup has NOT been executed. Review the items below and send {\"confirm\": true} to proceed.",
            "initiated_by": initiated_by,
            "items_to_delete": {
                "stale_acr_images": {
                    "count": len(stale_tags),
                    "tags": stale_tags,
                    "estimated_storage_freed_mb": len(stale_tags) * 150
                }
            },
            "protected_items": {
                "tags_kept": list(PROTECTED_TAGS),
                "active_resources": [r["resource_name"] for r in CLOUD_RESOURCES],
                "note": "These will NOT be affected"
            }
        })

    # ── Confirmed: execute cleanup ────────────────────────────────────────
    results = []
    for tag in stale_tags:
        result = delete_acr_image(tag)
        results.append(result)

    deleted_count = sum(1 for r in results if r["status"] == "deleted")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    storage_freed_mb = deleted_count * 150
    monthly_savings = round(deleted_count * 0.014, 2)

    # Log the cleanup action
    log_entry = {
        "timestamp": timestamp,
        "initiated_by": initiated_by,
        "images_deleted": deleted_count,
        "images_failed": failed_count,
        "storage_freed_mb": storage_freed_mb
    }
    cleanup_log.append(log_entry)
    print(f"[CLEANUP] {log_entry}")

    return jsonify({
        "cleanup_report": {
            "status": "completed",
            "timestamp": timestamp,
            "initiated_by": initiated_by,
            "resource_group": "nutritional-insights-rg",
            "region": "canadacentral"
        },
        "acr_cleanup": {
            "tags_processed": len(stale_tags),
            "tags_deleted": deleted_count,
            "tags_failed": failed_count,
            "protected_tags": list(PROTECTED_TAGS),
            "storage_freed_mb": storage_freed_mb,
            "monthly_savings_cad": monthly_savings,
            "details": results
        },
        "unused_project_files": {
            "note": "These files should be removed from the repo or added to .dockerignore",
            "items": UNUSED_PROJECT_FILES
        },
        "summary": {
            "before_cleanup_monthly_cost_cad": round(total_monthly_cost, 2),
            "storage_freed_mb": storage_freed_mb,
            "monthly_savings_from_cleanup_cad": monthly_savings,
            "after_cleanup_monthly_cost_cad": round(total_monthly_cost - monthly_savings, 2)
        }
    })


@app.route('/api/cleanup/log', methods=['GET'])
@token_required
def get_cleanup_log():
    """Returns the audit log of all cleanup operations performed."""
    return jsonify({
        "total_cleanups": len(cleanup_log),
        "log": cleanup_log
    })


# ---------------------------------------------------------------------------
# Server Startup
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
