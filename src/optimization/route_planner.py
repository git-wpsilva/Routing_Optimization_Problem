import pickle
import random

import networkx as nx
import osmnx as ox
import pandas as pd
from geopy.distance import geodesic

from utils.config import (
    DELIVERY_DAY,
    DELIVERY_HOUR,
    HOLIDAY,
)

ROAD_NETWORK_FILE = "data/output/road_network.pkl"
WAREHOUSE_COORDS = (-23.495652, -46.655389)
IGNORE_RESTRICTIONS = False  # Set to True to disable delivery constraints


def load_road_network():
    with open(ROAD_NETWORK_FILE, "rb") as f:
        return pickle.load(f)


def get_nearest_node(G, lat, lon):
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)


def is_vehicle_allowed(vehicle, delivery):
    if HOLIDAY or IGNORE_RESTRICTIONS:
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
        print(
            f"[BLOCKED] Vehicle {vehicle['license_plate']} not allowed in Rodízio for delivery {delivery['id']}"
        )
        return False

    if restriction == "VER" and not vehicle["allowed_in_ver"]:
        print(
            f"[BLOCKED] Vehicle {vehicle['license_plate']} not allowed in VER for delivery {delivery['id']}"
        )
        return False
    if restriction == "ZMRC" and not vehicle["allowed_in_zmrc"]:
        print(
            f"[BLOCKED] Vehicle {vehicle['license_plate']} not allowed in ZMRC for delivery {delivery['id']}"
        )
        return False

    if DELIVERY_DAY in time_rules:
        if DELIVERY_HOUR not in time_rules[DELIVERY_DAY]:
            print(
                f"[BLOCKED] Time restriction for delivery {delivery['id']} on {DELIVERY_DAY} at {DELIVERY_HOUR}h"
            )
            return False

    return True


def compute_shortest_path(G, warehouse_coords, deliveries):
    """
    Compute a robust and optimized TSP route:
    - Builds a virtual complete undirected graph with real shortest path distances
    - Solves the TSP over this graph
    - Reconstructs real route in G
    """
    from networkx.algorithms.approximation import traveling_salesman_problem

    warehouse_node = get_nearest_node(G, *warehouse_coords)
    delivery_nodes = [get_nearest_node(G, *dp["coords"]) for dp in deliveries]
    nodes = [warehouse_node] + delivery_nodes

    # Build complete virtual graph with shortest path distances
    tsp_graph = nx.Graph()
    for i, u in enumerate(nodes):
        for j, v in enumerate(nodes):
            if i >= j:
                continue
            try:
                dist = nx.shortest_path_length(G, u, v, weight="length")
                tsp_graph.add_edge(u, v, weight=dist)
            except nx.NetworkXNoPath:
                continue

    tsp_path = traveling_salesman_problem(tsp_graph, cycle=True, weight="weight")

    # Ensure route starts at warehouse
    while tsp_path[0] != warehouse_node:
        tsp_path = tsp_path[1:] + tsp_path[:1]

    # Reconstruct full route in G
    full_path = []
    total_distance = 0
    for i in range(len(tsp_path) - 1):
        a, b = tsp_path[i], tsp_path[i + 1]
        try:
            path = nx.shortest_path(G, a, b, weight="length")
            dist = nx.shortest_path_length(G, a, b, weight="length")
            full_path.extend(path[:-1])
            total_distance += dist
        except nx.NetworkXNoPath:
            continue

    full_path.append(tsp_path[-1])
    return full_path, total_distance


def assign_deliveries_to_routes(G, deliveries, vehicles):
    print("\n[OPTIMIZER] Assigning deliveries with heuristic optimization...")

    deliveries = sorted(
        deliveries,
        key=lambda d: (d["priority"], -d["weight_kg"], -d["volume_m3"]),
        reverse=True,
    )

    vehicles = sorted(
        vehicles,
        key=lambda v: (
            v["max_weight_kg"],
            v["length_m"] * v["width_m"] * v["height_m"],
        ),
        reverse=True,
    )

    assigned_deliveries = set()
    assignments = {}
    route_id = 1
    warehouse_node = get_nearest_node(G, *WAREHOUSE_COORDS)
    total_deliveries = len(deliveries)

    for vehicle in vehicles:
        if len(assigned_deliveries) == total_deliveries:
            break

        cap_weight = vehicle["max_weight_kg"]
        cap_volume = vehicle["length_m"] * vehicle["width_m"] * vehicle["height_m"]
        used_weight = 0
        used_volume = 0
        assigned = []
        delivery_nodes = {}

        print(f"\n[VEHICLE] {vehicle['license_plate']} | Type: {vehicle['type']}")

        for delivery in deliveries:
            delivery_node = get_nearest_node(G, *delivery["coords"])

            if delivery["id"] in assigned_deliveries:
                continue

            if not is_vehicle_allowed(vehicle, delivery):
                continue

            if not nx.has_path(G, warehouse_node, delivery_node):
                continue

            if delivery["weight_kg"] > (cap_weight - used_weight):
                continue

            if delivery["volume_m3"] > (cap_volume - used_volume):
                continue

            print(f" + Assigned delivery {delivery['id']} ({delivery['coords']})")
            assigned.append(delivery)
            delivery_nodes[delivery["id"]] = delivery_node
            used_weight += delivery["weight_kg"]
            used_volume += delivery["volume_m3"]
            assigned_deliveries.add(delivery["id"])

        if not assigned:
            continue

        path_nodes, total_distance = compute_shortest_path(
            G, WAREHOUSE_COORDS, assigned
        )

        assignments[f"Route {route_id}"] = {
            "vehicle": vehicle,
            "deliveries": assigned,
            "path": path_nodes,
            "distance_m": total_distance,
            "total_stops": len(assigned),
            "license_plate": vehicle["license_plate"],
            "delivery_nodes": delivery_nodes,
        }

        route_id += 1

    unassigned = [d for d in deliveries if d["id"] not in assigned_deliveries]
    if unassigned:
        print("\n[WARNING] Unassigned deliveries:")
        for d in unassigned:
            print(f" - ID {d['id']} | {d['coords']} | Priority: {d['priority']}")

    return assignments


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


def generate_distinct_colors(num_colors):
    """Generate a list of distinct colors."""
    colors = []
    for _ in range(num_colors):
        color = "#{:06x}".format(random.randint(0, 0xFFFFFF))
        colors.append(color)
    return colors


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


def generate_delivery_table(G, routes_data, vehicles, deliveries):
    """
    Create a detailed delivery route table with:
    - One row per stop (including START/END)
    - Route summary rows
    - Grand total row
    """
    rows = []
    total_weight = total_volume = total_distance = total_time = 0
    ASSUME_SPEED_KMPH = 30

    delivery_node_map = {get_nearest_node(G, *dp["coords"]): dp for dp in deliveries}

    mapped_nodes = set(delivery_node_map.keys())
    unmatched = [
        dp
        for dp in deliveries
        if get_nearest_node(G, *dp["coords"]) not in mapped_nodes
    ]
    if unmatched:
        print("WARNING: Some delivery points were not mapped to the route:")
        for u in unmatched:
            print(f"- ID {u['id']} at {u['coords']}")

    for route_index, (route_name, assignment) in enumerate(
        routes_data.items(), start=1
    ):
        vehicle = assignment["vehicle"]
        path_nodes = assignment["path"]
        vehicle_plate = assignment["vehicle"]["license_plate"]

        stop_counter = 0
        route_weight = 0
        route_volume = 0
        route_distance_km = round(assignment["distance_m"] / 1000, 2)
        route_time_hr = round(route_distance_km / ASSUME_SPEED_KMPH, 2)
        total_stops = assignment.get("total_stops", 0)

        # START point
        rows.append(
            [
                f"Route {route_index}",
                vehicle["id"],
                vehicle_plate,
                vehicle["type"],
                "START",
                "Warehouse",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                total_stops,
            ]
        )

        for node in path_nodes[1:-1]:
            matched_dp = delivery_node_map.get(node)
            if matched_dp:
                stop_counter += 1
                weight = matched_dp["weight_kg"]
                volume = matched_dp["volume_m3"]
                route_weight += weight
                route_volume += volume
                rows.append(
                    [
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
                        "",
                        "",
                        "",
                        "",
                        "",  # Ensure consistent number of columns
                    ]
                )

        # END point
        rows.append(
            [
                f"Route {route_index}",
                vehicle["id"],
                vehicle_plate,
                vehicle["type"],
                "END",
                "Warehouse",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )

        # Route summary row
        rows.append(
            [
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
                route_time_hr,
                "",
            ]
        )

        total_weight += route_weight
        total_volume += route_volume
        total_distance += route_distance_km
        total_time += route_time_hr

    # Global TOTAL row
    rows.append(
        [
            "TOTAL",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            total_weight,
            total_volume,
            "",
            "",
            total_distance,
            total_time,
            "",
        ]
    )

    df = pd.DataFrame(
        rows,
        columns=[
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
            "Time (hours)",
            "Total Stops",
        ],
    )

    csv_path = "data/output/delivery_routes.csv"
    df.to_csv(csv_path, index=False)
    print(f"Saved delivery route table → {csv_path}")
