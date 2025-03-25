import pickle
import random

import networkx as nx
import osmnx as ox
import pandas as pd
from geopy.distance import geodesic

from utils.config import (
    ASSUME_SPEED_KMPH,
    DELIVERY_DAY,
    DELIVERY_HOUR,
    HOLIDAY,
)

ROAD_NETWORK_FILE = "data/output/road_network.pkl"
WAREHOUSE_COORDS = (-23.495652, -46.655389)


def load_road_network():
    with open(ROAD_NETWORK_FILE, "rb") as f:
        return pickle.load(f)


def generate_distinct_colors(num_colors):
    """Generate a list of distinct colors."""
    colors = []
    for _ in range(num_colors):
        color = "#{:06x}".format(random.randint(0, 0xFFFFFF))
        colors.append(color)
    return colors


def get_nearest_node(G, lat, lon):
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)



def is_vehicle_allowed(vehicle, delivery):
    if HOLIDAY:
        return True

    restriction = delivery.get("restricted_area", None)
    time_rules = delivery.get("restriction_times", {})

    plate_digit = int(vehicle["license_plate"][-1])
    rodizio_map = {
        "Monday": {1, 2},
        "Tuesday": {3, 4},
        "Wednesday": {5, 6},
        "Thursday": {7, 8},
        "Friday": {9, 0},
    }

    if (
        restriction == "Rodízio Municipal"
        and DELIVERY_DAY in rodizio_map
        and plate_digit in rodizio_map[DELIVERY_DAY]
        and not vehicle["allowed_in_rodizio"]
    ):
        return False

    if restriction == "VER" and not vehicle["allowed_in_ver"]:
        return False
    if restriction == "ZMRC" and not vehicle["allowed_in_zmrc"]:
        return False

    if DELIVERY_DAY in time_rules:
        if DELIVERY_HOUR not in time_rules[DELIVERY_DAY]:
            return False

    return True


def find_closest_delivery(G, node, deliveries, max_distance_m=150):
    """Find the closest delivery to a given node within a threshold."""
    node_coord = (G.nodes[node]["y"], G.nodes[node]["x"])
    closest = None
    min_dist = float("inf")

    for d in deliveries:
        d_coord = tuple(d["coords"])
        dist = geodesic(node_coord, d_coord).meters
        if dist < min_dist and dist <= max_distance_m:
            closest = d
            min_dist = dist

    return closest


def assign_deliveries_to_routes(G, deliveries, vehicles):
    assignments = {}
    route_id = 1

    for vehicle in vehicles:
        vehicle_deliveries = []

        for delivery in deliveries:
            if is_vehicle_allowed(vehicle, delivery):
                if delivery["weight_kg"] <= vehicle["max_weight_kg"] and delivery[
                    "volume_m3"
                ] <= (vehicle["length_m"] * vehicle["width_m"] * vehicle["height_m"]):
                    vehicle_deliveries.append(delivery)

        if vehicle_deliveries:
            path_nodes, total_distance = compute_shortest_path(
                G, WAREHOUSE_COORDS, vehicle_deliveries
            )

            assignments[f"Route {route_id}"] = {
                "vehicle": vehicle,
                "deliveries": vehicle_deliveries,
                "path": path_nodes,
                "distance_m": total_distance,
            }

            route_id += 1

    return assignments


def compute_shortest_path(G, warehouse, delivery_coords):
    start = get_nearest_node(G, *warehouse)
    targets = [get_nearest_node(G, *d["coords"]) for d in delivery_coords]

    route = [start]
    distance = 0

    for node in targets:
        path = nx.shortest_path(G, route[-1], node, weight="length")
        segment_dist = nx.shortest_path_length(G, route[-1], node, weight="length")
        route += path[1:]
        distance += segment_dist

    path = nx.shortest_path(G, route[-1], start, weight="length")
    segment_dist = nx.shortest_path_length(G, route[-1], start, weight="length")
    route += path[1:]
    distance += segment_dist

    return route, distance


def plot_route(base_map, G, path_nodes, vehicle_label, color):
    from folium import FeatureGroup, PolyLine

    route_layer = FeatureGroup(
        name=f"Route - {vehicle_label}", overlay=True, control=True
    )

    coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in path_nodes]
    PolyLine(
        coords, color=color, weight=5, opacity=0.8, popup=f"Route for {vehicle_label}"
    ).add_to(route_layer)

    route_layer.add_to(base_map)
    return base_map

def generate_delivery_table(G, routes_data, vehicles, deliveries):
    """
    Create a detailed delivery route table with:
    - One row per stop (including START/END)
    - Route summary rows
    - Grand total row
    """

    rows = []
    route_totals = []
    total_weight = total_volume = total_distance = total_time = 0
    ASSUME_SPEED_KMPH = 30

    # 🚀 Precompute nearest node for each delivery point
    delivery_node_map = {
        get_nearest_node(G, *dp["coords"]): dp for dp in deliveries
    }

    mapped_nodes = set(delivery_node_map.keys())
    unmatched = [dp for dp in deliveries if get_nearest_node(G, *dp["coords"]) not in mapped_nodes]
    if unmatched:
        print("WARNING: Some delivery points were not mapped to the route:")
        for u in unmatched:
            print(f"- ID {u['id']} at {u['coords']}")


    for route_index, (vehicle_plate, assignment) in enumerate(routes_data.items(), start=1):
        vehicle = assignment["vehicle"]
        path_nodes = assignment["path"]
        delivery_points = assignment["deliveries"]

        stop_counter = 0
        route_weight = 0
        route_volume = 0
        route_distance_km = round(assignment["distance_m"] / 1000, 2)
        route_time_hr = round(route_distance_km / ASSUME_SPEED_KMPH, 2)

        # START point
        rows.append([
            f"Route {route_index}",
            vehicle["id"],
            vehicle_plate,
            vehicle["type"],
            "START",
            "Warehouse",
            "", "", "", "", "", "", "", ""
        ])

        for node in path_nodes[1:-1]:  # Ignore start/end nodes
            matched_dp = delivery_node_map.get(node)
            if matched_dp:
                stop_counter += 1
                weight = matched_dp["weight_kg"]
                volume = matched_dp["volume_m3"]
                route_weight += weight
                route_volume += volume
                rows.append([
                    f"Route {route_index}",
                    vehicle["id"],
                    vehicle_plate,
                    vehicle["type"],
                    f"STOP {stop_counter}",
                    matched_dp["id"],
                    matched_dp["coords"][0],
                    matched_dp["coords"][1],
                    weight,
                    volume,
                    "", "", "", ""
                ])

        # END point
        rows.append([
            f"Route {route_index}",
            vehicle["id"],
            vehicle_plate,
            vehicle["type"],
            f"END",
            "Warehouse",
            "", "", "", "", "", "", "", ""
        ])

        # Route summary row
        rows.append([
            f"Route {route_index} TOTAL",
            vehicle["id"],
            vehicle_plate,
            vehicle["type"],
            "",
            "",
            "",
            "",
            route_weight,
            route_volume,
            f"{(route_weight / vehicle['max_weight_kg']):.0%}",
            f"{(route_volume / (vehicle['length_m'] * vehicle['width_m'] * vehicle['height_m'])):.0%}",
            route_distance_km,
            route_time_hr
        ])

        # Update totals
        total_weight += route_weight
        total_volume += route_volume
        total_distance += route_distance_km
        total_time += route_time_hr

    # Global TOTAL row
    rows.append([
        "TOTAL",
        "", "", "", "", "", "", "",
        total_weight,
        total_volume,
        "", "", total_distance, total_time
    ])

    # Save as DataFrame
    df = pd.DataFrame(rows, columns=[
        "Route",
        "Vehicle ID",
        "License Plate",
        "Type",
        "Stop",
        "Delivery Point",
        "Latitude",
        "Longitude",
        "Weight (kg)",
        "Volume (m³)",
        "Weight %",
        "Volume %",
        "Distance (km)",
        "Time (hours)"
    ])

    csv_path = "data/output/delivery_routes.csv"
    df.to_csv(csv_path, index=False)
    print(f"Saved delivery route table → {csv_path}")
