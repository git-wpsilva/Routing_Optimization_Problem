import json
import os
import pickle

import geojson

EXPORT_PATH = "data/output/map_data_export.json"
GEOJSON_DIR = "data/output/routes_geojson"
CACHE_DIR = "data/output/cache"
RESTRICTION_INDEX_FILE = os.path.join(CACHE_DIR, "restriction_data.json")

os.makedirs(GEOJSON_DIR, exist_ok=True)


def export_map_data():
    """Export full map data from cached ETL and routing results."""
    print("\n[EXPORT] Starting map export...")

    with open(os.path.join(CACHE_DIR, "road_network.pkl"), "rb") as f:
        G = pickle.load(f)

    with open(
        os.path.join(CACHE_DIR, "vehicle_fleet.json"), "r", encoding="utf-8"
    ) as f:
        vehicles = json.load(f)

    with open(os.path.join(CACHE_DIR, "deliveries.json"), "r", encoding="utf-8") as f:
        deliveries = json.load(f)

    with open(os.path.join(CACHE_DIR, "assignments.json"), "r", encoding="utf-8") as f:
        assignments = json.load(f)

    export = {
        "warehouse": {"lat": -23.495652, "lon": -46.655389},
        "delivery_points": deliveries,
        "vehicles": vehicles,
        "restrictions": [],
        "routes": [],
    }

    # Load and export restriction zones from index
    if os.path.exists(RESTRICTION_INDEX_FILE):
        with open(RESTRICTION_INDEX_FILE, "r", encoding="utf-8") as f:
            restriction_index = json.load(f)

        for entry in restriction_index:
            filepath = entry["file"]
            if not os.path.exists(filepath):
                print(f"[WARNING] Restriction file not found: {filepath}")
                continue
            with open(filepath, "r", encoding="utf-8") as rf:
                restriction_geojson = json.load(rf)
                export["restrictions"].append(
                    {
                        "name": entry["name"],
                        "file": filepath,
                        "features": restriction_geojson.get("features", []),
                    }
                )

    # Gerar GeoJSON das rotas
    for route_id, assignment in assignments.items():
        vehicle = assignment["vehicle"]
        path_nodes = assignment["path"]
        distance = assignment["distance_m"]
        deliveries_for_vehicle = assignment["deliveries"]

        coords = []
        for node in path_nodes:
            if node in G.nodes:
                y = G.nodes[node].get("y")
                x = G.nodes[node].get("x")
                if y is not None and x is not None:
                    coords.append({"lat": y, "lon": x})

        geo_path = os.path.join(GEOJSON_DIR, f"route_{route_id}.geojson")
        line = geojson.LineString([(c["lon"], c["lat"]) for c in coords])
        feature = geojson.Feature(
            geometry=line,
            properties={
                "route_id": route_id,
                "vehicle_id": vehicle["id"],
                "license_plate": vehicle["license_plate"],
                "vehicle_type": vehicle["type"],
                "distance_km": round(distance / 1000, 2),
                "total_stops": len(deliveries_for_vehicle),
            },
        )
        with open(geo_path, "w") as f:
            geojson.dump(feature, f)

        export["routes"].append(
            {
                "route_id": route_id,
                "vehicle": vehicle,
                "distance_km": round(distance / 1000, 2),
                "path_nodes": path_nodes,
                "coordinates": coords,
                "geojson_file": geo_path,
            }
        )

    with open(EXPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    print(f"[EXPORT] Map data exported → {EXPORT_PATH}")
