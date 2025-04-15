import json
import os
import pickle

# File Paths
VEHICLE_FLEET_FILE = "data/input/vehicle_fleet.json"
ROAD_NETWORK_FILE = "data/output/road_network.pkl"
RESTRICTION_INDEX_FILE = "data/output/cache/restriction_data.json"
ENRICHED_RESTRICTIONS_DIR = "data/output/enriched"


def load_json(filepath):
    """Load a JSON file and return its content."""
    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)


def extract_vehicle_fleet():
    """Extract raw vehicle fleet data."""
    if not os.path.exists(VEHICLE_FLEET_FILE):
        raise FileNotFoundError(f"Error: {VEHICLE_FLEET_FILE} not found!")

    print("Extracting vehicle fleet data...")
    return load_json(VEHICLE_FLEET_FILE)["vehicles"]


def extract_road_network():
    """Extract raw road network data."""
    if not os.path.exists(ROAD_NETWORK_FILE):
        raise FileNotFoundError(f"Error: {ROAD_NETWORK_FILE} not found!")

    print("Extracting road network...")
    with open(ROAD_NETWORK_FILE, "rb") as f:
        return pickle.load(f)


def build_restriction_index_if_needed():
    """Create a restriction index JSON if it doesn't exist."""
    if os.path.exists(RESTRICTION_INDEX_FILE):
        print("Restriction index already exists.")
        return

    print("Generating restriction index...")
    os.makedirs(os.path.dirname(RESTRICTION_INDEX_FILE), exist_ok=True)

    restriction_data = []
    for filename in os.listdir(ENRICHED_RESTRICTIONS_DIR):
        if filename.endswith(".json"):
            name = filename.replace(".json", "").replace("_", " ").capitalize()
            restriction_data.append(
                {
                    "name": name,
                    "file": os.path.join(ENRICHED_RESTRICTIONS_DIR, filename),
                }
            )

    with open(RESTRICTION_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(restriction_data, f, indent=2, ensure_ascii=False)

    print(f"Restriction index created → {RESTRICTION_INDEX_FILE}")


# Run extraction


def run_extraction():
    """Run the extraction process."""
    extract_vehicle_fleet()
    extract_road_network()
    build_restriction_index_if_needed()


if __name__ == "__main__":
    run_extraction()
