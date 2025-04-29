import os
import pickle

import fiona
import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from networkx.algorithms.approximation import traveling_salesman_problem
from shapely.geometry import LineString, Point, shape

from etl.load import load_json
from utils.config import (
    CACHE_DIR,
    ROAD_NETWORK_FILE,
    WAREHOUSE_COORDS,
)

GPKG_PATH = os.path.join(CACHE_DIR, "routes.gpkg")
DEBUG_CLUSTER_CSV = os.path.join(CACHE_DIR, "cluster_debug.csv")
DELIVERY_AUDIT_PATH = os.path.join(CACHE_DIR, "debug_delivery_audit.csv")

def load_road_network():
    with open(ROAD_NETWORK_FILE, "rb") as f:
        return pickle.load(f)


def get_nearest_node(G, lat, lon):
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)


def is_vehicle_allowed_for_cluster(vehicle, cluster_meta):
    if vehicle.get("allowed_in_rodizio", True) and vehicle.get("allowed_in_zmrc", True):
        return True
    if (
        cluster_meta.get("requires_rodizio", False)
        and not vehicle["allowed_in_rodizio"]
    ):
        return False
    if cluster_meta.get("requires_zmrc", False) and not vehicle["allowed_in_zmrc"]:
        return False
    return True


def filter_graph_for_vehicle(G, vehicle):
    G_filtered = G.copy()

    path_zmrc = os.path.join(CACHE_DIR, "restriction_ZMRC.geojson")
    path_ver = os.path.join(CACHE_DIR, "restriction_Caminhão_1.geojson")

    zmrc = gpd.read_file(path_zmrc)
    ver = gpd.read_file(path_ver)

    zmrc_shape = shape(zmrc.geometry.iloc[0]).buffer(0)
    ver_shapes = [shape(geom) for geom in ver.geometry]

    nodes_to_remove = set()

    for node, data in G.nodes(data=True):
        point = Point(data["x"], data["y"])

        # ZMRC filtering
        if zmrc_shape.contains(point):
            if vehicle["type"] == "Truck":
                nodes_to_remove.add(node)
            if vehicle["type"] == "VUC" and not vehicle.get("has_aetc", False):
                nodes_to_remove.add(node)

        # VER filtering
        for ver_area in ver_shapes:
            if ver_area.contains(point):
                desc = ver.iloc[0]["Description"]
                if vehicle["type"] == "Truck":
                    nodes_to_remove.add(node)
                elif vehicle["type"] == "VUC":
                    if "VUC é PROIBIDO" in desc:
                        nodes_to_remove.add(node)

    G_filtered.remove_nodes_from(nodes_to_remove)
    return G_filtered


def compute_shortest_path_with_restrictions(
    G, warehouse_coords, delivery_points, vehicle
):

    G_vehicle = filter_graph_for_vehicle(G, vehicle)
    warehouse_node = get_nearest_node(G_vehicle, *warehouse_coords)

    delivery_nodes = []
    inaccessible_deliveries = []

    for d in delivery_points:
        try:
            delivery_node = get_nearest_node(G_vehicle, d["coords"][0], d["coords"][1])
            delivery_nodes.append(delivery_node)
        except Exception:
            inaccessible_deliveries.append(d["id"])

    if inaccessible_deliveries:
        for d_id in inaccessible_deliveries:
            print(
                f" Vehicle {vehicle['license_plate']} unable to access delivery {d_id} due to restrictions."
            )

    nodes = [warehouse_node] + delivery_nodes

    tsp_graph = nx.Graph()
    for i, u in enumerate(nodes):
        for j, v in enumerate(nodes):
            if i >= j:
                continue
            try:
                dist = nx.shortest_path_length(G_vehicle, u, v, weight="length")
                tsp_graph.add_edge(u, v, weight=dist)
            except nx.NetworkXNoPath:
                continue

    expected_edges = len(tsp_graph.nodes) * (len(tsp_graph.nodes) - 1) // 2
    if len(tsp_graph.edges) < expected_edges:
        raise ValueError("Cannot create TSP path: disconnected or incomplete graph")

    tsp_path = traveling_salesman_problem(tsp_graph, cycle=True, weight="weight")

    while tsp_path[0] != warehouse_node:
        tsp_path = tsp_path[1:] + tsp_path[:1]

    full_path = []
    total_distance = 0
    for i in range(len(tsp_path) - 1):
        a, b = tsp_path[i], tsp_path[i + 1]
        try:
            path = nx.shortest_path(G_vehicle, a, b, weight="length")
            dist = nx.shortest_path_length(G_vehicle, a, b, weight="length")
            full_path.extend(path[:-1])
            total_distance += dist
        except nx.NetworkXNoPath:
            continue

    full_path.append(tsp_path[-1])
    return full_path, total_distance


def try_assign_cluster_to_alternate_vehicle(
    G, vehicles, assigned_deliveries, used_vehicles
):
    """Try to assign deliveries to an alternate vehicle if the original cannot complete the route."""

    for alt_vehicle in vehicles:
        if alt_vehicle["license_plate"] in used_vehicles:
            continue

        try:
            path_nodes, total_distance = compute_shortest_path_with_restrictions(
                G,
                WAREHOUSE_COORDS,
                [item["delivery"] for item in assigned_deliveries],
                alt_vehicle,
            )
            return alt_vehicle, path_nodes, total_distance
        except ValueError:
            continue

    return None, None, None


def assign_clusters_to_routes(G, vehicles):
    print("\n[OPTIMIZER] Assigning clusters with smart heuristic optimization...")

    deliveries = load_json(os.path.join(CACHE_DIR, "deliveries.json"))
    deliveries_dict = {d["id"]: d for d in deliveries}

    df_debug = pd.read_csv(DEBUG_CLUSTER_CSV)
    cluster_mapping = df_debug.groupby("cluster_id")["delivery_id"].apply(list).to_dict()

    cluster_meta = {}
    GPKG_CLUSTER_PATH = os.path.join(CACHE_DIR, "delivery_clusters.gpkg")
    if os.path.exists(GPKG_CLUSTER_PATH):
        cluster_layers = fiona.listlayers(GPKG_CLUSTER_PATH)
        for layer_name in cluster_layers:
            gdf = gpd.read_file(GPKG_CLUSTER_PATH, layer=layer_name)
            if not gdf.empty:
                cluster_meta[layer_name] = {
                    "requires_zmrc": bool(gdf.iloc[0].get("requires_zmrc", False)),
                    "requires_rodizio": bool(gdf.iloc[0].get("requires_rodizio", False)),
                }

    vehicles = sorted(
        vehicles,
        key=lambda v: (v["max_weight_kg"], v["length_m"] * v["width_m"] * v["height_m"]),
        reverse=True,
    )

    assignments = {}
    route_id = 1
    used_deliveries = set()
    pending_deliveries = []

    for cluster_id, delivery_ids in cluster_mapping.items():
        cluster_deliveries = [deliveries_dict[did] for did in delivery_ids if did not in used_deliveries]
        if not cluster_deliveries:
            continue

        assigned = False
        for vehicle in vehicles:
            if not can_vehicle_reach_all_deliveries(G, vehicle, cluster_deliveries):
                continue
            try:
                path_nodes, total_distance = compute_shortest_path_with_restrictions(
                    G, WAREHOUSE_COORDS, cluster_deliveries, vehicle
                )
            except ValueError:
                continue
            if not validate_route_efficiency(G, cluster_deliveries, path_nodes):
                continue

            assignments[f"Route {route_id}"] = {
                "vehicle": vehicle,
                "path": path_nodes,
                "distance_m": total_distance,
                "deliveries": [
                    {"delivery": d, "cluster_id": cluster_id} for d in cluster_deliveries
                ],
            }
            used_deliveries.update([d["id"] for d in cluster_deliveries])
            print(f"[ASSIGNMENT] Vehicle {vehicle['license_plate']} assigned {len(cluster_deliveries)} deliveries for {cluster_id}.")
            route_id += 1
            assigned = True
            break

        if not assigned:
            for d in cluster_deliveries:
                d["cluster_id"] = f"Reassigned from {cluster_id}"
            pending_deliveries.extend(cluster_deliveries)

    if pending_deliveries:
        print(f"[CRITICAL] {len(pending_deliveries)} deliveries remain pending. Re-attempting assignment...")
        extra_assignments = assign_remaining_deliveries_to_vehicles(G, vehicles, pending_deliveries)
        assignments.update(extra_assignments)

    return assignments


def assign_remaining_deliveries_to_vehicles(G, vehicles, remaining_deliveries):
    """Assign any remaining deliveries to available vehicles, respecting weight and volume intelligently."""
    assignments = {}
    route_id = 2000  # Start new route IDs from 2000 to separate from main assignments

    deliveries_list = list(remaining_deliveries)
    {d["id"]: d for d in deliveries_list}

    vehicles_sorted = sorted(
        vehicles,
        key=lambda v: (
            v["max_weight_kg"],
            v["length_m"] * v["width_m"] * v["height_m"],
        ),
        reverse=True,
    )

    used_deliveries = set()

    for vehicle in vehicles_sorted:
        cap_weight = vehicle["max_weight_kg"]
        cap_volume = vehicle["length_m"] * vehicle["width_m"] * vehicle["height_m"]
        used_weight = 0
        used_volume = 0
        assigned_deliveries = []

        for delivery in deliveries_list:
            if delivery["id"] in used_deliveries:
                continue

            weight = delivery.get("weight_kg", 0)
            volume = delivery.get("volume_m3", 0)

            if (used_weight + weight <= cap_weight) and (
                used_volume + volume <= cap_volume
            ):
                assigned_deliveries.append(
                    {
                        "delivery": delivery,
                        "cluster_id": delivery.get("cluster_id", "Unclustered"),
                    }
                )
                used_deliveries.add(delivery["id"])
                used_weight += weight
                used_volume += volume

        if not assigned_deliveries:
            continue

        try:
            path_nodes, total_distance = compute_shortest_path_with_restrictions(
                G,
                WAREHOUSE_COORDS,
                [item["delivery"] for item in assigned_deliveries],
                vehicle,
            )
        except ValueError:
            print(
                f"[WARNING] Could not create route for vehicle {vehicle['license_plate']} with remaining deliveries."
            )
            continue

        assignments[f"Route {route_id}"] = {
            "vehicle": vehicle,
            "path": path_nodes,
            "distance_m": total_distance,
            "deliveries": assigned_deliveries,
        }

        print(
            f"[ASSIGNMENT] (Remaining) Vehicle {vehicle['license_plate']} assigned {len(assigned_deliveries)} deliveries."
        )
        route_id += 1

        if len(used_deliveries) == len(deliveries_list):
            break  # All remaining deliveries assigned

    not_assigned = len(deliveries_list) - len(used_deliveries)
    if not_assigned > 0:
        print(
            f"[WARNING] {not_assigned} deliveries could not be assigned to any vehicle."
        )

    return assignments


def can_vehicle_reach_all_deliveries(G, vehicle, deliveries):
    """Quickly check if a vehicle can reach all delivery points."""
    G_vehicle = filter_graph_for_vehicle(G, vehicle)
    for d in deliveries:
        try:
            _ = get_nearest_node(G_vehicle, d["coords"][0], d["coords"][1])
        except Exception:
            return False
    return True


def validate_route_efficiency(G, deliveries, path_nodes, threshold=1.5):
    """Validate if the real route is not excessively longer than straight-line distance."""
    if len(deliveries) < 2:
        return True  # Ignore small deliveries

    warehouse_point = Point(WAREHOUSE_COORDS[1], WAREHOUSE_COORDS[0])
    delivery_points = [Point(d["coords"][1], d["coords"][0]) for d in deliveries]

    # Straight-line distance (approximate)
    straight_distance = sum(warehouse_point.distance(dp) for dp in delivery_points)

    # Real path distance
    real_distance = 0
    for i in range(len(path_nodes) - 1):
        if path_nodes[i] in G.nodes and path_nodes[i + 1] in G.nodes:
            try:
                real_distance += nx.shortest_path_length(
                    G, path_nodes[i], path_nodes[i + 1], weight="length"
                )
            except:
                pass

    if real_distance == 0:
        return False

    ratio = real_distance / straight_distance

    return ratio <= threshold


def plot_route(base_map, G, path_nodes, vehicle_label, color):
    from folium import FeatureGroup, PolyLine

    coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in path_nodes if n in G.nodes]

    if len(coords) < 2:
        print(f"[WARNING] Skipping plot for route {vehicle_label}: not enough valid coordinates.")
        return base_map

    route_layer = FeatureGroup(name=f"Route - {vehicle_label}", overlay=True, control=True)
    PolyLine(coords, color=color, weight=5, opacity=0.8, popup=f"Route for {vehicle_label}").add_to(route_layer)
    route_layer.add_to(base_map)
    return base_map


def generate_delivery_table(G, routes_data):
    rows = []
    ASSUME_SPEED_KMPH = 30

    for route_name, assignment in routes_data.items():
        vehicle = assignment["vehicle"]
        deliveries = assignment.get("deliveries", [])
        total_weight = sum(d["delivery"].get("weight_kg", 0) for d in deliveries)
        total_volume = sum(d["delivery"].get("volume_m3", 0) for d in deliveries)
        total_distance_km = round(assignment["distance_m"] / 1000, 2)
        total_time_hr = round(total_distance_km / ASSUME_SPEED_KMPH, 2)

        rows.append([route_name, vehicle["id"], vehicle["license_plate"], vehicle["type"], "START", "Warehouse", "", "", "", "", "", "", "", "", ])

        for stop_counter, delivery_entry in enumerate(deliveries, start=1):
            d = delivery_entry["delivery"]
            cluster_id = delivery_entry["cluster_id"]
            rows.append([
                route_name,
                vehicle["id"],
                vehicle["license_plate"],
                vehicle["type"],
                f"STOP {stop_counter}",
                d["id"],
                d["coords"][0],
                d["coords"][1],
                d.get("weight_kg", 0),
                d.get("volume_m3", 0),
                cluster_id,
                "", "", "", "",
            ])

        rows.append([route_name, vehicle["id"], vehicle["license_plate"], vehicle["type"], "END", "Warehouse", "", "", "", "", "", "", "", "", ])
        rows.append([
            route_name + " TOTAL", "", "", "", "", "", "", "", total_weight, total_volume, "",
            f"{(total_weight / vehicle['max_weight_kg']):.0%}",
            f"{(total_volume / (vehicle['length_m'] * vehicle['width_m'] * vehicle['height_m'])):.0%}",
            total_distance_km, total_time_hr
        ])

    df = pd.DataFrame(rows, columns=[
        "Route", "Vehicle ID", "License Plate", "Type", "Stop", "Delivery Point",
        "Latitude", "Longitude", "Weight (kg)", "Volume (m³)", "Cluster ID",
        "Weight %", "Volume %", "Distance (km)", "Time (hours)"
    ])
    df.to_csv("data/output/delivery_routes.csv", index=False)
    print("[EXPORT] Saved detailed delivery routes → data/output/delivery_routes.csv")

def save_routes_to_geopackage(G, routes_data):
    if os.path.exists(GPKG_PATH):
        os.remove(GPKG_PATH)

    for route_name, assignment in routes_data.items():
        path_nodes = assignment["path"]
        coords = [(G.nodes[n]["x"], G.nodes[n]["y"]) for n in path_nodes if n in G.nodes]

        delivery_coords = [
            (d["delivery"]["coords"][1], d["delivery"]["coords"][0])
            for d in assignment["deliveries"]
        ]
        all_coords = coords + [pt for pt in delivery_coords if pt not in coords]

        if len(all_coords) < 2:
            print(f"[WARNING] Skipping {route_name}: not enough points to form a path.")
            continue

        try:
            line = LineString(all_coords)
        except Exception as e:
            print(f"[ERROR] Failed to create LineString for {route_name}: {e}")
            continue

        visited_ids = [d["delivery"]["id"] for d in assignment["deliveries"]]

        gdf = gpd.GeoDataFrame([
            {
                "route_id": route_name,
                "vehicle_id": assignment["vehicle"]["id"],
                "license_plate": assignment["vehicle"]["license_plate"],
                "geometry": line,
                "distance_km": round(assignment["distance_m"] / 1000, 2),
                "total_stops": len(visited_ids),
                "visited_ids": ",".join(map(str, visited_ids))
            }
        ], crs="EPSG:4326")

        gdf.to_file(GPKG_PATH, layer=route_name, driver="GPKG")
        print(f"[GPKG] Route {route_name} saved.")


def audit_delivery_integrity():
    print("\n[DEBUG] Starting delivery integrity audit...")

    deliveries = load_json(os.path.join(CACHE_DIR, "deliveries.json"))
    all_ids = {str(d["id"]) for d in deliveries}

    df_csv = pd.read_csv("data/output/delivery_routes.csv")
    ids_csv = set(df_csv[df_csv["Delivery Point"].notnull()]["Delivery Point"].astype(str))

    ids_gpkg = set()
    if os.path.exists(GPKG_PATH):
        layers = fiona.listlayers(GPKG_PATH)
        for layer in layers:
            gdf = gpd.read_file(GPKG_PATH, layer=layer)
            for entry in gdf.get("visited_ids", []):
                if isinstance(entry, str):
                    ids_gpkg.update(entry.split(","))

    all_ids_combined = all_ids.union(ids_csv).union(ids_gpkg)

    rows = []
    for id_ in sorted(all_ids_combined, key=lambda x: int(x) if x.isdigit() else float('inf')):
        rows.append({
            "Delivery ID": id_,
            "In Deliveries JSON": "Yes" if id_ in all_ids else "No",
            "In CSV": "Yes" if id_ in ids_csv else "No",
            "In GPKG": "Yes" if id_ in ids_gpkg else "No",
        })

    df_result = pd.DataFrame(rows)
    df_result["Observation"] = df_result.apply(
        lambda row: "Missing in GPKG" if row["In CSV"] == "Yes" and row["In GPKG"] == "No"
        else ("Missing in CSV" if row["In GPKG"] == "Yes" and row["In CSV"] == "No"
        else ("Not assigned" if row["In CSV"] == "No" and row["In GPKG"] == "No" and row["In Deliveries JSON"] == "Yes"
        else "OK")), axis=1
    )

    df_result.to_csv(DELIVERY_AUDIT_PATH, index=False)
    print(f"[DEBUG] Audit table saved → {DELIVERY_AUDIT_PATH}")
