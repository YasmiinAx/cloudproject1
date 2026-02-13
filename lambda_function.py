import os
import io
import json
from datetime import datetime
import pandas as pd
from azure.storage.blob import BlobServiceClient
 
# Hardcoded Azurite connection string for local simulation
AZURITE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFeqCnrC4xF6JCXzqnYXY955klpCyG3CnxOTjVMYPXMvRhhzWdg==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)
 
CONTAINER_NAME = "datasets"
BLOB_NAME = "All_Diets.csv"
OUTPUT_PATH = os.path.join("simulated_nosql", "results.json")
 
def process_nutritional_data_from_azurite():
    print("Connecting to Azurite...")
    # Corrected initialization: uses the explicit string and a compatible API version
    blob_service = BlobServiceClient.from_connection_string(
        AZURITE_CONNECTION_STRING, 
        api_version="2019-12-12"
    )
 
    container_client = blob_service.get_container_client(CONTAINER_NAME)
    blob_client = container_client.get_blob_client(BLOB_NAME)
 
    print(f"Downloading {BLOB_NAME} from Blob storage...")
    data = blob_client.download_blob().readall()
    df = pd.read_csv(io.BytesIO(data))
 
    # Data Processing: ensuring numeric types and cleaning missing values
    for col in ["Protein(g)", "Carbs(g)", "Fat(g)"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.fillna(df.mean(numeric_only=True), inplace=True)
 
    # Calculation of averages per Diet Type
    avg_macros = (
        df.groupby("Diet_type")[["Protein(g)", "Carbs(g)", "Fat(g)"]]
        .mean()
        .reset_index()
    )
 
    # Creating the JSON payload for simulated NoSQL storage
    payload = {
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "source": {"container": CONTAINER_NAME, "blob": BLOB_NAME},
        "avg_macros_by_diet": avg_macros.to_dict(orient="records"),
    }
 
    # Save to JSON file as per task requirements
    os.makedirs("simulated_nosql", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
 
    return payload
 
if __name__ == "__main__":
    try:
        result = process_nutritional_data_from_azurite()
        print(f"Success! Results saved to {OUTPUT_PATH}.")
        print(f"Total Diets processed: {len(result['avg_macros_by_diet'])}")
    except Exception as e:
        print(f"An error occurred: {e}")