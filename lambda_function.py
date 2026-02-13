import os
import io
import json
from datetime import datetime
import pandas as pd
from azure.storage.blob import BlobServiceClient

AZURITE_CONNECTION_STRING = "UseDevelopmentStorage=true"

CONTAINER_NAME = "datasets"
BLOB_NAME = "All_Diets.csv"
OUTPUT_PATH = os.path.join("simulated_nosql", "results.json")

def process_nutritional_data_from_azurite():
    blob_service = BlobServiceClient.from_connection_string(
        AZURITE_CONNECTION_STRING
    )

    container_client = blob_service.get_container_client(CONTAINER_NAME)
    blob_client = container_client.get_blob_client(BLOB_NAME)

    data = blob_client.download_blob().readall()

    df = pd.read_csv(io.BytesIO(data))

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

    print("Results saved to simulated_nosql/results.json")
    print("Diets processed:", len(payload["avg_macros_by_diet"]))

    return payload


if __name__ == "__main__":
    print(process_nutritional_data_from_azurite())