import os
import folium

from etl.extract import extract_road_network, extract_vehicle_fleet
from mapping.delivery_points import generate_random_delivery_points, plot_delivery_points
from mapping.restrictions_map import plot_restrictions
from optimization.route_planner import (
    assign_deliveries_to_routes,
    compute_shortest_path,
    generate_delivery_table,
    plot_route,
    find_closest_delivery,
)

# Constants
MAP_OUTPUT_DIR = "data/output/maps"
STEPS_DIR = os.path.join(MAP_OUTPUT_DIR, "steps")
FINAL_MAP_PATH = os.path.join(MAP_OUTPUT_DIR, "route_plan_map.html")
WAREHOUSE_COORDS = (-23.495652, -46.655389)

# Ensure output dirs exist
os.makedirs(STEPS_DIR, exist_ok=True)

def save_map(base_map, step_name):
    """Save an intermediate step of the map."""
    step_map_path = os.path.join(STEPS_DIR, f"{step_name}.html")
    base_map.save(step_map_path)
    print(f"Step saved: {step_map_path}")

def main():
    print("Loading road network and vehicles...")
    G = extract_road_network()
    vehicles = extract_vehicle_fleet()

    print("Generating delivery points...")
    deliveries = generate_random_delivery_points(num_points=10)

    print("Initializing base map...")
    base_map = folium.Map(location=[-23.495652, -46.655389], zoom_start=12)

    print("Adding restriction zones...")
    base_map = plot_restrictions(base_map)
    save_map(base_map, "01_restrictions")

    print("Plotting delivery points and warehouse...")
    base_map = plot_delivery_points(base_map, deliveries)
    save_map(base_map, "02_delivery_points")

    print("Assigning routes and generating delivery table...")
    assignments = assign_deliveries_to_routes(G, deliveries, vehicles)

    routes_data = {}
    for route_number, assignment in assignments.items():
        vehicle = assignment["vehicle"]
        deliveries_for_vehicle = assignment["deliveries"]
        path_nodes, distance = compute_shortest_path(G, WAREHOUSE_COORDS, deliveries_for_vehicle)

        routes_data[route_number] = {
            "vehicle": vehicle,
            "path": path_nodes,
            "distance_m": distance,
            "deliveries": deliveries_for_vehicle,
        }

        base_map = plot_route(base_map, G, path_nodes, vehicle["license_plate"], route_number)

    generate_delivery_table(G, routes_data, vehicles, deliveries)
    save_map(base_map, "03_routes")

    print("Final map saved.")
    base_map.save(FINAL_MAP_PATH)

if __name__ == "__main__":
    main()
