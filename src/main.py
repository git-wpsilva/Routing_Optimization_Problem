import os
import folium
from etl.extract import extract_road_network, extract_vehicle_fleet
from mapping.delivery_points import generate_random_delivery_points, plot_delivery_points
from mapping.restrictions_map import plot_restrictions
from optimization.route_planner import run_optimized_routing
from utils.daytime_config import set_global_delivery_context

# Constants
MAP_OUTPUT_DIR = "data/output/maps"
STEPS_DIR = os.path.join(MAP_OUTPUT_DIR, "steps")
FINAL_MAP_PATH = os.path.join(MAP_OUTPUT_DIR, "route_plan_map.html")

# Ensure output dirs exist
os.makedirs(STEPS_DIR, exist_ok=True)

def save_map(base_map, step_name):
    path = os.path.join(STEPS_DIR, f"{step_name}.html")
    base_map.save(path)
    print(f"Step saved: {path}")

def main():
    print("Extracting road network and vehicle fleet...")
    G = extract_road_network()
    vehicles = extract_vehicle_fleet()

    print("Setting delivery context (day, hour, holiday)...")
    set_global_delivery_context(day="Tuesday", hour=10, is_holiday=False)  # 🔧 Adjustable params

    print("Generating delivery points...")
    deliveries = generate_random_delivery_points(num_points=10)

    print("Initializing base map...")
    base_map = folium.Map(location=[-23.495652, -46.655389], zoom_start=12)

    print("Adding restriction zones...")
    base_map = plot_restrictions(base_map)
    save_map(base_map, "01_restrictions")

    print("Adding delivery points and warehouse...")
    base_map = plot_delivery_points(base_map, num_points=10)
    save_map(base_map, "02_delivery_points")

    print("Computing optimized routes...")
    base_map = run_optimized_routing(base_map, G, vehicles, deliveries)
    save_map(base_map, "03_routes")

    print("Final map saved.")
    base_map.save(FINAL_MAP_PATH)

if __name__ == "__main__":
    main()
