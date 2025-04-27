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
from optimization.delivery_clustering import generate_delivery_clusters
from optimization.route_planner import (
    assign_deliveries_to_routes,
    compute_shortest_path,
    generate_delivery_table,
    plot_route,
)
from utils.config import (
    CACHE_DIR,
    DEBUG_ROUTE_PATH,
    FINAL_MAP_PATH,
    ROUTES_GEOJSON_DIR,
    STEPS_DIR,
    WAREHOUSE_COORDS,
)


def log_step(message):
    print(f"\n=== {message} ===")


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
    geo_path = os.path.join(ROUTES_GEOJSON_DIR, f"route_{route_id}.geojson")
    with open(geo_path, "w") as f:
        geojson.dump(feature, f)
    print(f"[GEOJSON] Saved route → {geo_path}")


def main():
    log_step("Running transformation pipeline")
    run_transformation()

    log_step("Loading road network and vehicles")
    build_restriction_index_if_needed()
    G = extract_road_network()
    vehicles = extract_vehicle_fleet()

    with open(os.path.join(CACHE_DIR, "road_network.pkl"), "wb") as f:
        pickle.dump(G, f)
    with open(
        os.path.join(CACHE_DIR, "vehicle_fleet.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(vehicles, f, indent=2, ensure_ascii=False)

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
    generate_delivery_clusters()

    log_step("Plotting delivery clusters")
    base_map = plot_clusters_on_map(base_map)
    save_map(base_map, os.path.join(STEPS_DIR, "04_clusters.html"))

    log_step("Assigning routes and generating delivery table")
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


if __name__ == "__main__":
    main()
