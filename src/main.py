import json
import os

import folium
import pandas as pd

from etl.extract import (
    build_restriction_index_if_needed,
    extract_road_network,
    extract_vehicle_fleet,
)
from etl.load import save_map
from etl.transform import run_transformation
from mapping.cluster_map import plot_clusters_on_map
from mapping.delivery_points import (
    generate_random_delivery_points,
    plot_delivery_points,
)
from mapping.generate_qgis_project import generate_qgis_project
from mapping.map_data_export import export_map_data
from mapping.restrictions_map import plot_restrictions
from optimization.assign_clusters_heuristic import assign_clusters_heuristic
from optimization.route_planner import (
    audit_delivery_integrity,
    generate_delivery_table,
    plot_route,
    save_routes_to_geopackage,
)
from utils.config import (
    CACHE_DIR,
    DEBUG_ROUTE_PATH,
    FINAL_MAP_PATH,
    STEPS_DIR,
)


def log_step(message):
    print(f"\n=== {message} ===")


def main():
    log_step("Running transformation pipeline")
    run_transformation()

    log_step("Loading road network and vehicles")
    build_restriction_index_if_needed()
    G = extract_road_network()
    vehicles = extract_vehicle_fleet()

    log_step("Generating delivery points")
    deliveries = generate_random_delivery_points(G, num_points=20)
    with open(os.path.join(CACHE_DIR, "deliveries.json"), "w", encoding="utf-8") as f:
        json.dump(deliveries, f, indent=2, ensure_ascii=False)

    log_step("Initializing base map")
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

    log_step("Plotting restriction zones")
    base_map = plot_restrictions(base_map)
    save_map(base_map, os.path.join(STEPS_DIR, "01_restrictions.html"))

    log_step("Plotting delivery points and warehouse")
    base_map = plot_delivery_points(base_map, deliveries)
    save_map(base_map, os.path.join(STEPS_DIR, "02_delivery_points.html"))

    log_step("Generating delivery clusters")
    from optimization.delivery_clustering import generate_delivery_clusters

    generate_delivery_clusters()

    log_step("Plotting delivery clusters")
    base_map = plot_clusters_on_map(base_map)
    save_map(base_map, os.path.join(STEPS_DIR, "04_clusters.html"))

    log_step("Assigning clusters to vehicles and generating routes")
    assignments = assign_clusters_heuristic(G, vehicles)

    debug_rows = []
    for route_number, assignment in assignments.items():
        vehicle = assignment["vehicle"]
        path_nodes = assignment["path"]
        distance = assignment["distance_m"]

        print(f"[DEBUG] Route {route_number} has {len(path_nodes)} nodes in path.")
        plot_route(base_map, G, path_nodes, route_number, color=route_number[-1])

        debug_rows.append(
            {
                "Route": f"Route {route_number}",
                "Vehicle ID": vehicle["id"],
                "License Plate": vehicle["license_plate"],
                "Type": vehicle["type"],
                "Distance (km)": round(distance / 1000, 2),
            }
        )

    generate_delivery_table(G, assignments)
    save_routes_to_geopackage(G, assignments)
    save_map(base_map, os.path.join(STEPS_DIR, "03_routes.html"))

    folium.LayerControl().add_to(base_map)

    log_step("Saving debug route CSV")
    df_debug = pd.DataFrame(debug_rows)
    df_debug.to_csv(DEBUG_ROUTE_PATH, index=False)
    print(f"[DEBUG] Saved debug table → {DEBUG_ROUTE_PATH}")

    log_step("Saving final map and exporting")
    save_map(base_map, FINAL_MAP_PATH)
    export_map_data()
    generate_qgis_project()
    print("[QGIS] Project exported successfully")

    log_step("Running delivery audit")
    audit_delivery_integrity()



if __name__ == "__main__":
    main()
