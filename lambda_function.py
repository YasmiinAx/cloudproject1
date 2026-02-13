import os
import json
from datetime import datetime
import pandas as pd

CONTAINER_NAME = "datasets"
BLOB_NAME = "All_Diets.csv"
OUTPUT_PATH = os.path.join("simulated_nosql", "results.json")

def process_nutritional_data_local():
    df = pd.read_csv("All_Diets.csv")

    for col in ["Protein(g)", "Carbs(g)", "Fat(g)"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df.fillna(df.mean(numeric_only=True), inplace=True)

    avg_macros = (
        df.groupby("Diet_type")[["Protein(g)", "Carbs(g)", "Fat(g)"]]
        .mean()
        .reset_index()
    )

    payload = {
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "source": {"container": CONTAINER_NAME, "blob": BLOB_NAME},
        "avg_macros_by_diet": avg_macros.to_dict(orient="records"),
    }

    os.makedirs("simulated_nosql", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return payload

if __name__ == "__main__":
    result = process_nutritional_data_local()
    print(f"Results saved to {OUTPUT_PATH}.")
    print(f"Diets processed: {len(result['avg_macros_by_diet'])}")
