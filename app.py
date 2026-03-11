# This is a simple Flask backend for a diet recipe application. It provides three API endpoints:
# 
# 1. /api/insights: Returns average macros (protein, carbs, fat
#    for each diet type to show in the "Insights" section of the UI.
# 
# 2. /api/recipes: Returns a list of recipes filtered by diet type based
#    on the user's selection in the dropdown menu in the UI.
# 
# 3. /api/clusters: Performs KMeans clustering on the recipes based on their
#    macros and returns the cluster assignments to show in the "Clusters" section of the UI.

from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
from sklearn.cluster import KMeans

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Data source provided by Member 3 (Azure Blob Storage)
DATA_SOURCE = "https://dietanalysiscpsy.blob.core.windows.net/datasets/All_Diets.csv" 

def load_data():
    df = pd.read_csv(DATA_SOURCE)
    # Handle missing values by filling with mean (for simplicity)
    df.fillna(df.mean(numeric_only=True), inplace=True)
    return df

@app.route('/api/insights', methods=['GET'])
def get_insights():
    df = load_data()
    avg_macros = df.groupby("Diet_type")[["Protein(g)", "Carbs(g)", "Fat(g)"]].mean().reset_index()
    # Convert to a list of dictionaries for the Frontend
    return jsonify(avg_macros.to_dict(orient='records'))

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    df = load_data()
    diet = request.args.get('diet')
    # Filter recipes based on the selected diet type (if not 'All Diet Types')
    if diet and diet != 'All Diet Types':
        # Convert to lowercase for case-insensitive comparison
        df = df[df['Diet_type'].str.lower() == diet.lower()]
    return jsonify(df.head(50).to_dict(orient='records'))

@app.route('/api/clusters', methods=['GET'])
def get_clusters():
    df = load_data()
    # Perform KMeans clustering based on macros (Protein, Carbs, Fat)
    km = KMeans(n_clusters=3, random_state=42)
    df['cluster'] = km.fit_predict(df[["Protein(g)", "Carbs(g)", "Fat(g)"]])
    return jsonify(df[['Recipe_name', 'Diet_type', 'cluster']].head(50).to_dict(orient='records'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)