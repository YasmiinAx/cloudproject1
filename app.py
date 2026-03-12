# This is a simple Flask backend for a diet recipe application. It provides three API endpoints:
# 
# 1. /api/insights: Returns average macros (protein, carbs, fat)
#    for each diet type to show in the "Insights" section of the UI.
# 
# 2. /api/recipes: Returns a list of recipes filtered by diet type based
#    on the user's selection in the dropdown menu in the UI.
# 
# 3. /api/clusters: Performs KMeans clustering on the recipes based on their
#    macros and returns the cluster assignments to show in the "Clusters" section of the UI.

import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pandas as pd
from sklearn.cluster import KMeans

app = Flask(__name__, static_folder='static')

# ---------------------------------------------------------------------------
# CORS Configuration (Security Best Practice)
# ---------------------------------------------------------------------------
# Only allow requests from our own domain + localhost during development.
# CORS(app) with no arguments would allow ANY website to call our API — bad.
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = [
    "http://localhost:5000",
    "http://127.0.0.1:5000",
]

# If deployed on Azure, allow the Azure domain too
AZURE_APP_NAME = os.environ.get("WEBSITE_HOSTNAME")  # Azure injects this automatically
if AZURE_APP_NAME:
    ALLOWED_ORIGINS.append(f"https://{AZURE_APP_NAME}")

CORS(app, origins=ALLOWED_ORIGINS)

# Data source provided by Member 3 (Azure Blob Storage)
DATA_SOURCE = "https://dietanalysiscpsy.blob.core.windows.net/datasets/All_Diets.csv"

# ---------------------------------------------------------------------------
# Cache the dataframe so we don't re-download the CSV on every single request
# ---------------------------------------------------------------------------
_df_cache = None

def load_data():
    global _df_cache
    if _df_cache is None:
        df = pd.read_csv(DATA_SOURCE)
        df.fillna(df.mean(numeric_only=True), inplace=True)
        _df_cache = df
    return _df_cache.copy()

# ---------------------------------------------------------------------------
# Serve the frontend dashboard
# ---------------------------------------------------------------------------
@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'index.html')

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.route('/api/insights', methods=['GET'])
def get_insights():
    df = load_data()
    avg_macros = df.groupby("Diet_type")[["Protein(g)", "Carbs(g)", "Fat(g)"]].mean().reset_index()
    return jsonify(avg_macros.to_dict(orient='records'))

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    df = load_data()
    diet = request.args.get('diet')
    if diet and diet != 'All Diet Types':
        df = df[df['Diet_type'].str.lower() == diet.lower()]
    return jsonify(df.to_dict(orient='records'))

@app.route('/api/clusters', methods=['GET'])
def get_clusters():
    df = load_data()
    km = KMeans(n_clusters=3, random_state=42)
    df['cluster'] = km.fit_predict(df[["Protein(g)", "Carbs(g)", "Fat(g)"]])
    return jsonify(df[['Recipe_name', 'Diet_type', 'cluster']].to_dict(orient='records'))

# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # debug=False in production. host=0.0.0.0 so Docker/Azure can reach it.
    app.run(host="0.0.0.0", port=port, debug=False)
