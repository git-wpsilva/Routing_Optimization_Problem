import json
import os
import pickle

import folium
import geojson
import pandas as pd

from etl.extract import (
    build_restriction_index_if_needed,
    extract_road_network,
    extract_vehicle_fleet,
)
from mapping.delivery_points import (
    generate_random_delivery_points,
    plot_delivery_points,
)
from mapping.generate_qgis_project import generate_qgis_project
from mapping.map_data_export import export_map_data
from mapping.restrictions_map import plot_restrictions
from optimization.route_planner import (
    assign_deliveries_to_routes,
    compute_shortest_path,
    generate_delivery_table,
    plot_route,
)

# Constants
MAP_OUTPUT_DIR = "data/output/maps"
GEOJSON_DIR = "data/output/routes_geojson"
CACHE_DIR = "data/output/cache"
STEPS_DIR = os.path.join(MAP_OUTPUT_DIR, "steps")
FINAL_MAP_PATH = os.path.join(MAP_OUTPUT_DIR, "route_plan_map.html")
WAREHOUSE_COORDS = (-23.495652, -46.655389)
DEBUG_ROUTE_PATH = "data/output/debug_routes.csv"

# Ensure output dirs exist
os.makedirs(STEPS_DIR, exist_ok=True)
os.makedirs(GEOJSON_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)


def save_map(base_map, step_name):
    """Save an intermediate step of the map."""
    step_map_path = os.path.join(STEPS_DIR, f"{step_name}.html")
    base_map.save(step_map_path)
    print(f"Step saved: {step_map_path}")


def save_geojson_route(route_id, coords, vehicle, distance, num_stops):
    """Save the route coordinates as a GeoJSON LineString."""
    line = geojson.LineString([(lon, lat) for lat, lon in coords])
    feature = geojson.Feature(
        geometry=line,
        properties={
            "route_id": route_id,
            "vehicle_id": vehicle["id"],
            "license_plate": vehicle["license_plate"],
            "vehicle_type": vehicle["type"],
            "distance_km": round(distance / 1000, 2),
            "total_stops": num_stops,
        },
    )
    geo_path = os.path.join(GEOJSON_DIR, f"route_{route_id}.geojson")
    with open(geo_path, "w") as f:
        geojson.dump(feature, f)
    print(f"[GEOJSON] Saved route → {geo_path}")


def main():
    print("Loading road network and vehicles...")
    build_restriction_index_if_needed()
    G = extract_road_network()
    vehicles = extract_vehicle_fleet()

    # Cache G and vehicles
    with open(os.path.join(CACHE_DIR, "road_network.pkl"), "wb") as f:
        pickle.dump(G, f)
    with open(
        os.path.join(CACHE_DIR, "vehicle_fleet.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(vehicles, f, indent=2, ensure_ascii=False)

    print("Generating delivery points...")
    deliveries = generate_random_delivery_points(G, num_points=10)
    with open(os.path.join(CACHE_DIR, "deliveries.json"), "w", encoding="utf-8") as f:
        json.dump(deliveries, f, indent=2, ensure_ascii=False)

    print("Initializing base map...")
    all_coords = [
        (data["y"], data["x"])
        for node, data in G.nodes(data=True)
        if "x" in data and "y" in data
    ]
    if all_coords:
        avg_lat = sum(p[0] for p in all_coords) / len(all_coords)
        avg_lon = sum(p[1] for p in all_coords) / len(all_coords)
        base_map = folium.Map(location=[avg_lat, avg_lon], zoom_start=12)
    else:
        base_map = folium.Map(location=[-23.495652, -46.655389], zoom_start=12)

    print("Adding restriction zones...")
    base_map = plot_restrictions(base_map)
    save_map(base_map, "01_restrictions")

    print("Plotting delivery points and warehouse...")
    base_map = plot_delivery_points(base_map, deliveries)
    save_map(base_map, "02_delivery_points")

    print("Assigning routes and generating delivery table...")
    assignments = assign_deliveries_to_routes(G, deliveries, vehicles)
    with open(os.path.join(CACHE_DIR, "assignments.json"), "w", encoding="utf-8") as f:
        json.dump(assignments, f, indent=2, ensure_ascii=False)

    debug_rows = []
    routes_data = {}
    for route_number, assignment in assignments.items():
        vehicle = assignment["vehicle"]
        deliveries_for_vehicle = assignment["deliveries"]
        path_nodes, distance = compute_shortest_path(
            G, WAREHOUSE_COORDS, deliveries_for_vehicle
        )

        routes_data[route_number] = {
            "vehicle": vehicle,
            "path": path_nodes,
            "distance_m": distance,
            "deliveries": deliveries_for_vehicle,
        }

        route_coords = []
        for node in path_nodes:
            if node in G.nodes:
                y = G.nodes[node].get("y")
                x = G.nodes[node].get("x")
                if y is not None and x is not None:
                    route_coords.append((y, x))

        if route_coords:
            save_geojson_route(
                route_number,
                route_coords,
                vehicle,
                distance,
                len(deliveries_for_vehicle),
            )

        plot_route(base_map, G, path_nodes, vehicle["license_plate"], route_number)

        debug_rows.append(
            {
                "Route": f"Route {route_number}",
                "Vehicle ID": vehicle["id"],
                "License Plate": vehicle["license_plate"],
                "Type": vehicle["type"],
                "Path Nodes": path_nodes,
                "Distance (km)": round(distance / 1000, 2),
                "Total Stops": len(deliveries_for_vehicle),
            }
        )

    generate_delivery_table(G, routes_data, vehicles, deliveries)
    save_map(base_map, "03_routes")

    folium.LayerControl().add_to(base_map)

    print("Saving debug route CSV...")
    df_debug = pd.DataFrame(debug_rows)
    df_debug.to_csv(DEBUG_ROUTE_PATH, index=False)
    print(f"Saved debug table → {DEBUG_ROUTE_PATH}")

    print("Final map saved.")
    base_map.save(FINAL_MAP_PATH)

    # Call export after everything is cached
    export_map_data()
    generate_qgis_project()
    print(f"QGIS project saved")


if __name__ == "__main__":
    main()
