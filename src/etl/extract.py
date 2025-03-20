import json
import os
import pickle

# File Paths
VEHICLE_FLEET_FILE = "data/input/vehicle_fleet.json"
ROAD_NETWORK_FILE = "data/output/road_network.pkl"

def load_json(filepath):
    """Load a JSON file and return its content."""
    with open(filepath, 'r', encoding='utf-8') as file:
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

# Run extraction
def run_extraction():
    """Run the extraction process."""
    extract_vehicle_fleet()
    extract_road_network()

if __name__ == "__main__":
    run_extraction()
