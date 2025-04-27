import json
import os
import pickle

from etl.load import load_json
from utils.config import (
    CACHE_DIR,
    RESTRICTION_INDEX_FILE,
    ROAD_NETWORK_FILE,
    VEHICLE_FLEET_FILE,
)


def extract_vehicle_fleet():
    if not os.path.exists(VEHICLE_FLEET_FILE):
        raise FileNotFoundError(f"Error: {VEHICLE_FLEET_FILE} not found!")

    print("Extracting vehicle fleet data...")
    return load_json(VEHICLE_FLEET_FILE)["vehicles"]


def extract_road_network():
    if not os.path.exists(ROAD_NETWORK_FILE):
        raise FileNotFoundError(f"Error: {ROAD_NETWORK_FILE} not found!")

    print("Extracting road network...")
    with open(ROAD_NETWORK_FILE, "rb") as f:
        return pickle.load(f)


def build_restriction_index_if_needed():
    if os.path.exists(RESTRICTION_INDEX_FILE):
        print("[SKIP] Restriction index already exists.")
        return

    print("Generating restriction index...")
    os.makedirs(os.path.dirname(RESTRICTION_INDEX_FILE), exist_ok=True)

    restriction_data = []
    for filename in os.listdir(CACHE_DIR):
        if filename.startswith("restriction_") and filename.endswith(".geojson"):
            name = (
                filename.replace("restriction_", "")
                .replace(".geojson", "")
                .replace("_", " ")
                .title()
            )
            restriction_data.append(
                {
                    "name": name,
                    "file": os.path.join(CACHE_DIR, filename).replace("\\", "/"),
                }
            )

    with open(RESTRICTION_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(restriction_data, f, indent=2, ensure_ascii=False)

    print(f"[OK] Restriction index created → {RESTRICTION_INDEX_FILE}")


def run_extraction():
    extract_vehicle_fleet()
    extract_road_network()
    build_restriction_index_if_needed()


if __name__ == "__main__":
    run_extraction()
