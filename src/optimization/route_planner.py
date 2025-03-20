import pickle
import json
import networkx as nx
import osmnx as ox
import folium
import pandas as pd
import numpy as np
import random
import os
from sklearn.cluster import KMeans

# Constants
ROAD_NETWORK_FILE = "data/output/road_network.pkl"
VEHICLE_FLEET_FILE = "data/input/vehicle_fleet.json"
WAREHOUSE_COORDS = (-23.495652, -46.655389)  # Warehouse start point

def load_road_network():
    """Load the processed road network."""
    with open(ROAD_NETWORK_FILE, "rb") as f:
        return pickle.load(f)

def get_nearest_node(G, lat, lon):
    """Find the nearest graph node to a given latitude/longitude."""
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)

def load_vehicle_fleet():
    """Load vehicle fleet from JSON file and return a list of vehicles."""
    with open(VEHICLE_FLEET_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data["vehicles"]

def cluster_deliveries(deliveries, num_vehicles):
    """Use K-Means to cluster deliveries into vehicle-specific regions."""
    num_clusters = min(len(deliveries), num_vehicles)

    if num_clusters == 1:
        return {0: deliveries}  

    coords = np.array([d["coords"] for d in deliveries])
    kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(coords)

    clusters = {i: [] for i in range(num_clusters)}
    for i, delivery in enumerate(deliveries):
        clusters[labels[i]].append(delivery)

    return clusters

def assign_deliveries_to_vehicles(deliveries, vehicles):
    """Assign deliveries to the best-suited vehicle based on constraints."""
    assigned_routes = {v["license_plate"]: [] for v in vehicles}

    # Sort deliveries by priority and weight (largest first)
    deliveries = sorted(deliveries, key=lambda d: (-["High", "Medium", "Low"].index(d["priority"]), -d["weight_kg"]))

    for delivery in deliveries:
        for vehicle in vehicles:
            # Check weight and volume constraints
            if delivery["weight_kg"] <= vehicle["max_weight_kg"] and delivery["volume_m3"] <= (vehicle["length_m"] * vehicle["width_m"] * vehicle["height_m"]):
                # Check if vehicle is allowed in the area
                if not (vehicle["allowed_in_rodizio"] or vehicle["allowed_in_zmrc"] or vehicle["allowed_in_ver"]):
                    continue  # Skip vehicle if it's restricted
                
                # Assign delivery to this vehicle
                assigned_routes[vehicle["license_plate"]].append(delivery)
                break  # Move to next delivery

    return assigned_routes

def initial_grasp_solution(G, warehouse, deliveries):
    """Construct initial VRP solution using GRASP."""
    nodes = [get_nearest_node(G, *warehouse)]  # Warehouse node

    for lat, lon in deliveries:  # ✅ Fix: Unpack tuple directly
        nodes.append(get_nearest_node(G, lat, lon))

    best_order = None
    best_distance = float("inf")

    for _ in range(20):
        random.shuffle(nodes[1:])
        distance = sum(nx.shortest_path_length(G, nodes[i], nodes[i+1], weight="length") for i in range(len(nodes) - 1))

        if distance < best_distance:
            best_distance = distance
            best_order = nodes[:]

    return best_order, best_distance



def two_opt(route, G):
    """Optimize route using 2-opt heuristic."""
    best_route = route
    best_distance = sum(nx.shortest_path_length(G, best_route[i], best_route[i+1], weight="length") for i in range(len(route) - 1))

    for i in range(1, len(route) - 2):
        for j in range(i + 1, len(route) - 1):
            new_route = best_route[:i] + best_route[i:j][::-1] + best_route[j:]
            new_distance = sum(nx.shortest_path_length(G, new_route[k], new_route[k+1], weight="length") for k in range(len(new_route) - 1))

            if new_distance < best_distance:
                best_route = new_route
                best_distance = new_distance

    return best_route, best_distance

def plot_route(base_map, G, order, vehicle):
    """Overlay the computed route on the existing map."""
    route_layer = folium.FeatureGroup(name=f"Optimized Route - {vehicle}")

    route_coords = [(G.nodes[node]["y"], G.nodes[node]["x"]) for node in order]

    folium.PolyLine(route_coords, color="blue", weight=5, opacity=0.7, popup=f"{vehicle} Route").add_to(route_layer)

    base_map.add_child(route_layer)

    return base_map  # Return updated map

def generate_delivery_table(routes):
    """Generate a route table with vehicle, delivery points, and distance."""
    data = []
    for vehicle, (order, distance) in routes.items():
        formatted_order = " → ".join([f"Point {i+1}" for i in range(len(order) - 1)])
        time = round(distance / 30 * 60, 1)  
        data.append([vehicle, formatted_order, len(order) - 1, round(distance / 1000, 2), time])

    df = pd.DataFrame(data, columns=["Vehicle", "Route", "Stops", "Distance (km)", "Time (min)"])
    csv_path = "data/output/delivery_routes.csv"
    df.to_csv(csv_path, index=False)
    print(f"Delivery route table saved as {csv_path}")

def run_optimized_routing(base_map, G, vehicles, deliveries):
    """Run the full advanced routing pipeline with vehicle selection."""
    print("Assigning deliveries to vehicles...")
    vehicle_routes = assign_deliveries_to_vehicles(deliveries, vehicles)

    print("Finding optimal routes...")
    routes = {}

    for vehicle_id, deliveries in vehicle_routes.items():
        if not deliveries:
            continue

        delivery_coords = [d["coords"] for d in deliveries]

        initial_order, initial_distance = initial_grasp_solution(G, WAREHOUSE_COORDS, delivery_coords)
        optimized_order, optimized_distance = two_opt(initial_order, G)

        routes[vehicle_id] = (optimized_order, optimized_distance)
        base_map = plot_route(base_map, G, optimized_order, vehicle_id)

    generate_delivery_table(routes)
    print("All optimized routes computed and saved.")

    return base_map  # Return the updated map
