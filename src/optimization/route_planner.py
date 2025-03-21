import pickle

import folium
import networkx as nx
import osmnx as ox
import pandas as pd
from geopy.distance import geodesic

# Constants
ROAD_NETWORK_FILE = "data/output/road_network.pkl"
VEHICLE_FLEET_FILE = "data/input/vehicle_fleet.json"
WAREHOUSE_COORDS = (-23.495652, -46.655389)  # Warehouse start point
DELIVERY_DAY = "Tuesday"  # Options: Monday, Tuesday, ..., Sunday
DELIVERY_HOUR = 10  # Integer hour (0–23)
HOLIDAY = False  # Set to True if it's a public holiday


def load_road_network():
    """Load the processed road network."""
    with open(ROAD_NETWORK_FILE, "rb") as f:
        return pickle.load(f)


def get_nearest_node(G, lat, lon):
    """Find the nearest graph node to a given latitude/longitude."""
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)


def is_vehicle_allowed(vehicle, delivery):
    """
    Check if a vehicle is allowed to make a delivery considering:
    - Rodízio restriction (day, time, plate number)
    - Zone restrictions (VER, ZMRC)
    - Holidays (exempt from restrictions)
    - Time-based restrictions
    Returns True if the vehicle can legally deliver to this point.
    """
    if HOLIDAY:
        return True  # 🚀 Holiday: No restrictions apply!

    delivery_restriction = delivery.get("restricted_area", None)
    restriction_times = delivery.get("restriction_times", None)  # Time-based rules

    # ✅ Step 1: Check Rodízio Restriction (Plate Last Digit)
    rodizio_days = {
        "Monday": {1, 2},
        "Tuesday": {3, 4},
        "Wednesday": {5, 6},
        "Thursday": {7, 8},
        "Friday": {9, 0},
    }

    plate_last_digit = int(vehicle["license_plate"][-1])  # Get last digit of plate
    if (
        delivery_restriction == "Rodízio Municipal"
        and DELIVERY_DAY in rodizio_days
        and plate_last_digit in rodizio_days[DELIVERY_DAY]
        and not vehicle["allowed_in_rodizio"]
    ):
        return False  # 🚫 Restricted by Rodízio

    # ✅ Step 2: Zone Restrictions (VER, ZMRC)
    if (delivery_restriction == "VER" and not vehicle["allowed_in_ver"]) or (
        delivery_restriction == "ZMRC" and not vehicle["allowed_in_zmrc"]
    ):
        return False  # 🚫 Restricted by Zone

    # ✅ Step 3: Time-Based Restrictions
    if restriction_times:
        allowed_hours = restriction_times.get(DELIVERY_DAY, [])
        if allowed_hours and DELIVERY_HOUR not in allowed_hours:
            return False  # 🚫 Restricted by Time

    return True


def assign_deliveries_to_vehicles(deliveries, vehicles):
    """
    Assign deliveries to the most suitable vehicle based on weight, volume, and restrictions.
    Ensures fair distribution and avoids repeating deliveries.
    """
    assigned_routes = {v["license_plate"]: [] for v in vehicles}
    unassigned_deliveries = []  # Track deliveries that cannot be assigned

    # 🚨 Sort deliveries by priority first (High > Medium > Low), then by weight (heaviest first)
    priority_map = {"High": 3, "Medium": 2, "Low": 1}
    deliveries = sorted(
        deliveries, key=lambda d: (-priority_map[d["priority"]], -d["weight_kg"])
    )

    for delivery in deliveries:
        best_vehicle = None
        min_unused_capacity = float("inf")

        for vehicle in vehicles:
            remaining_capacity = vehicle["max_weight_kg"] - sum(
                d["weight_kg"] for d in assigned_routes[vehicle["license_plate"]]
            )

            # ✅ Vehicle must have enough capacity & respect delivery restrictions
            if (
                remaining_capacity >= delivery["weight_kg"]
                and delivery["volume_m3"]
                <= (vehicle["length_m"] * vehicle["width_m"] * vehicle["height_m"])
                and delivery.get("restricted_area", None)
                in [
                    None,
                    vehicle["allowed_in_zmrc"],
                    vehicle["allowed_in_ver"],
                    vehicle["allowed_in_rodizio"],
                ]
            ):
                # ✅ Select the vehicle with the least remaining capacity (better load balancing)
                if remaining_capacity < min_unused_capacity:
                    best_vehicle = vehicle
                    min_unused_capacity = remaining_capacity

        if best_vehicle:
            assigned_routes[best_vehicle["license_plate"]].append(delivery)
        else:
            unassigned_deliveries.append(delivery)  # 🚨 Log unassigned deliveries

    # 🚨 Notify about unassigned deliveries
    if unassigned_deliveries:
        print(
            "\nWARNING: The following deliveries could not be assigned due to capacity/restrictions:"
        )
        for d in unassigned_deliveries:
            print(
                f"Delivery {d['id']} at {d['coords']} (Weight: {d['weight_kg']} kg, Volume: {d['volume_m3']} m³)"
            )

    return assigned_routes


def compute_realistic_routes(G, warehouse, deliveries):
    """Compute vehicle routes using real shortest paths."""
    if not deliveries:
        print("WARNING: No deliveries for this vehicle!")
        return [], 0  # Return empty route

    warehouse_node = get_nearest_node(G, *warehouse)
    delivery_nodes = [get_nearest_node(G, *d["coords"]) for d in deliveries]

    if not delivery_nodes:
        print("ERROR: No valid delivery nodes found!")
        return [], 0

    # ✅ Ensure unique delivery points per route
    delivery_nodes = list(set(delivery_nodes))

    nodes = (
        [warehouse_node] + delivery_nodes + [warehouse_node]
    )  # Start & end at warehouse
    total_distance = 0
    full_route = []

    try:
        for i in range(len(nodes) - 1):
            segment = nx.shortest_path(
                G, source=nodes[i], target=nodes[i + 1], weight="length"
            )
            segment_distance = nx.shortest_path_length(
                G, source=nodes[i], target=nodes[i + 1], weight="length"
            )

            full_route.extend(segment[:-1])  # Avoid duplicating nodes
            total_distance += segment_distance

        full_route.append(nodes[-1])  # Add last node

    except Exception as e:
        print(f"ERROR computing shortest path: {e}")
        return [], 0

    print(f"\nDEBUG: Computed Route (Nodes): {full_route}")
    print(f"DEBUG: Total Distance: {total_distance} meters")

    return full_route, total_distance


def plot_route(base_map, G, order, vehicle):
    """Overlay the computed route on the existing map."""
    route_layer = folium.FeatureGroup(name=f"Optimized Route - {vehicle}")

    route_coords = [(G.nodes[node]["y"], G.nodes[node]["x"]) for node in order]

    folium.PolyLine(
        route_coords, color="blue", weight=5, opacity=0.7, popup=f"{vehicle} Route"
    ).add_to(route_layer)

    base_map.add_child(route_layer)
    return base_map


def find_closest_delivery(G, node, deliveries, max_distance_m=100):
    """Finds the closest delivery point to a given route node within a tolerance distance."""
    node_coords = (G.nodes[node]["y"], G.nodes[node]["x"])

    for d in deliveries:
        delivery_coords = tuple(d["coords"])
        if geodesic(node_coords, delivery_coords).meters <= max_distance_m:
            return d
    return None


def generate_delivery_table(routes, vehicles, G, deliveries):
    """Generate a detailed delivery route table with correct delivery mappings."""
    data = []

    for vehicle_id, (route_nodes, distance) in routes.items():
        vehicle_info = next(
            (v for v in vehicles if v["license_plate"] == vehicle_id), None
        )
        if not vehicle_info:
            continue

        vehicle_type = vehicle_info["type"]
        formatted_stops = []

        stop_count = 1
        for node in route_nodes[1:-1]:  # Ignore warehouse start & end
            delivery_point = find_closest_delivery(G, node, deliveries)
            if delivery_point:
                formatted_stops.append(
                    f"Stop {stop_count} → Delivery Point {deliveries.index(delivery_point) + 1}"
                )
                stop_count += 1

        formatted_route = (
            " → ".join(formatted_stops) if formatted_stops else "No Deliveries"
        )
        time_hours = round(distance / 1000 / 30, 2)

        data.append(
            [
                vehicle_info["id"],
                vehicle_id,
                vehicle_type,
                formatted_route,
                len(formatted_stops),
                round(distance / 1000, 2),
                time_hours,
            ]
        )

    df = pd.DataFrame(
        data,
        columns=[
            "Vehicle ID",
            "License Plate",
            "Type",
            "Route",
            "Stops",
            "Distance (km)",
            "Time (hours)",
        ],
    )
    csv_path = "data/output/delivery_routes.csv"
    df.to_csv(csv_path, index=False)
    print(f"Updated Delivery Route Table → {csv_path}")


def run_optimized_routing(base_map, G, vehicles, deliveries):
    """Run the full advanced routing pipeline with vehicle selection and realistic paths."""
    print("Assigning deliveries to vehicles...")
    vehicle_routes = assign_deliveries_to_vehicles(deliveries, vehicles)

    print("Finding optimal routes...")
    routes = {}

    for vehicle_id, deliveries in vehicle_routes.items():
        if not deliveries:
            continue

        delivery_coords = [d["coords"] for d in deliveries]

        ordered_route, total_distance = compute_realistic_routes(
            G, WAREHOUSE_COORDS, delivery_coords
        )

        routes[vehicle_id] = (ordered_route, total_distance)
        base_map = plot_route(base_map, G, ordered_route, vehicle_id)

    generate_delivery_table(routes, vehicles, G, deliveries)
    print("All optimized routes computed and saved.")

    return base_map


def create_delivery_points_table(G, deliveries):
    """
    Create a table of delivery points with their details and a total row.

    Parameters:
    - G: NetworkX graph representing the road network.
    - deliveries: List of dictionaries, each containing 'id', 'coords', 'weight_kg', and 'volume_m3'.

    Returns:
    - DataFrame with delivery details and a total row.
    """
    data = []

    for delivery in deliveries:
        delivery_id = delivery.get("id")
        coords = delivery.get("coords")
        weight = delivery.get("weight_kg", 0)
        volume = delivery.get("volume_m3", 0)
        nearest_node = get_nearest_node(G, *coords)

        data.append(
            {
                "Delivery ID": delivery_id,
                "Latitude": coords[0],
                "Longitude": coords[1],
                "Nearest Node": nearest_node,
                "Weight (kg)": weight,
                "Volume (m³)": volume,
            }
        )

    df = pd.DataFrame(data)

    # Calculate totals
    total_weight = df["Weight (kg)"].sum()
    total_volume = df["Volume (m³)"].sum()

    # Append total row
    total_row = pd.DataFrame(
        {
            "Delivery ID": ["Total"],
            "Latitude": [None],
            "Longitude": [None],
            "Nearest Node": [None],
            "Weight (kg)": [total_weight],
            "Volume (m³)": [total_volume],
        }
    )

    df = pd.concat([df, total_row], ignore_index=True)

    # Save to CSV
    csv_path = "data/output/delivery_points_table.csv"
    df.to_csv(csv_path, index=False)
    print(f"Delivery Points Table saved to {csv_path}")

    return df


def generate_delivery_table(G, routes, vehicles, deliveries):
    """Generate a structured route summary table with stops properly numbered per route."""
    data = []
    route_counter = 1  # Unique route numbering

    for vehicle_id, (route_nodes, distance) in routes.items():
        vehicle_info = next(
            (v for v in vehicles if v["license_plate"] == vehicle_id), None
        )
        if not vehicle_info:
            continue  # Skip if vehicle not found

        vehicle_type = vehicle_info["type"]
        formatted_stops = []
        stop_counter = 1  # Reset stop count per route

        for node in route_nodes[1:-1]:  # Ignore warehouse start & end
            delivery_point = next(
                (d for d in deliveries if get_nearest_node(G, *d["coords"]) == node),
                None,
            )
            if delivery_point:
                formatted_stops.append(
                    f"STOP {stop_counter}: Delivery Point {delivery_point['id']}"
                )
                stop_counter += 1

        formatted_route = (
            " → ".join(formatted_stops) if formatted_stops else "No Deliveries"
        )
        time_hours = round(distance / 1000 / 30, 2)  # Assume 30 km/h speed

        data.append(
            [
                f"Route {route_counter}",  # Unique Route ID
                vehicle_info["id"],
                vehicle_id,
                vehicle_type,
                formatted_route,
                len(formatted_stops),
                round(distance / 1000, 2),
                time_hours,
            ]
        )

        route_counter += 1  # Increment route count

    df = pd.DataFrame(
        data,
        columns=[
            "Route",
            "Vehicle ID",
            "License Plate",
            "Type",
            "Route",
            "Stops",
            "Distance (km)",
            "Time (hours)",
        ],
    )

    csv_path = "data/output/delivery_routes.csv"
    df.to_csv(csv_path, index=False)
    print(f"Updated Delivery Route Table → {csv_path}")
