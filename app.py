import os
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from sklearn.cluster import KMeans

app = Flask(__name__, static_folder='static')
CORS(app) 

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
def get_insights():
    df = load_data()
    diet = request.args.get('diet')
    if diet and diet.lower() != "all":
        df = df[df['Diet_type'].str.lower() == diet.lower()]
    
    if df.empty: return jsonify([])
    
    avg_macros = df.groupby("Diet_type")[["Protein(g)", "Carbs(g)", "Fat(g)"]].mean().reset_index()
    return jsonify(avg_macros.to_dict(orient='records'))

@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    df = load_data()
    diet = request.args.get('diet')
    if diet and diet.lower() != "all":
        df = df[df['Diet_type'].str.lower() == diet.lower()]
    
    if df.empty: return jsonify([])
    
    num_samples = min(len(df), 50)    
    return jsonify(df.sample(num_samples, random_state=42).to_dict(orient='records'))

@app.route('/api/clusters', methods=['GET'])
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