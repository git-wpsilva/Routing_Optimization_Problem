import osmnx as ox
import networkx as nx
import json
import pickle

RESTRICTIONS_FILE = "data/input/restrictions/restrictions.json"

def load_restrictions():
    """Load restrictions from JSON."""
    with open(RESTRICTIONS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

def build_road_network():
    """Download São Paulo's road network directly using OSMNX."""
    print("Downloading São Paulo's road network from OSM...")

    # Define bounding box for São Paulo (around 15km delivery area)
    place_name = "São Paulo, Brazil"
    G = ox.graph_from_place(place_name, network_type="drive")  # Loads the full road network

    print("Processing restrictions...")
    restrictions = load_restrictions()

    # Iterate over edges to mark restricted roads
    for u, v, key, data in G.edges(keys=True, data=True):
        road_name = data.get("name", "")
        if isinstance(road_name, list):  
            road_name = " ".join(road_name)  # Convert list to string
        road_name = road_name.lower()

        if any(zone.lower() in road_name for zone in restrictions["rodizio_municipal"]["affected_area"]["boundaries"]):
            data["restricted"] = True
            data["restriction_type"] = "Rodízio Municipal"

        elif "ver" in road_name:
            data["restricted"] = True
            data["restriction_type"] = "VER"

        elif "zmrc" in road_name:
            data["restricted"] = True
            data["restriction_type"] = "ZMRC"

        else:
            data["restricted"] = False

    print("Saving processed road network...")
    with open("data/output/road_network.pkl", "wb") as f: pickle.dump(G, f)
    print("Road network saved!")

if __name__ == "__main__":
    build_road_network()
