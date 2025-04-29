import os
import pickle

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import Point, shape

from etl.load import load_json
from utils.config import (
    CACHE_DIR,
    DEBUG_CLUSTER_CSV,
    ROAD_NETWORK_FILE,
    WAREHOUSE_COORDS,
)


def load_road_network():
    with open(ROAD_NETWORK_FILE, "rb") as f:
        return pickle.load(f)

def get_nearest_node(G, lat, lon):
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)

def prepare_restriction_shapes():
    path_zmrc = os.path.join(CACHE_DIR, "restriction_ZMRC.geojson")
    path_ver = os.path.join(CACHE_DIR, "restriction_Caminhão_1.geojson")
    zmrc = gpd.read_file(path_zmrc)
    ver = gpd.read_file(path_ver)
    zmrc_shape = shape(zmrc.geometry.iloc[0]).buffer(0)
    ver_shapes = [shape(geom) for geom in ver.geometry]
    return zmrc_shape, ver_shapes, ver

def filter_graph_for_vehicle(G, vehicle, zmrc_shape, ver_shapes, ver):
    G_filtered = G.copy()
    nodes_to_remove = set()
    for node, data in G.nodes(data=True):
        point = Point(data["x"], data["y"])
        if zmrc_shape.contains(point):
            if vehicle["type"] == "Truck":
                nodes_to_remove.add(node)
            if vehicle["type"] == "VUC" and not vehicle.get("has_aetc", False):
                nodes_to_remove.add(node)
        for ver_area in ver_shapes:
            if ver_area.contains(point):
                desc = ver.iloc[0]["Description"]
                if vehicle["type"] == "Truck":
                    nodes_to_remove.add(node)
                elif vehicle["type"] == "VUC" and "VUC é PROIBIDO" in desc:
                    nodes_to_remove.add(node)
    G_filtered.remove_nodes_from(nodes_to_remove)
    return G_filtered

def can_vehicle_reach_delivery(G_vehicle, delivery):
    try:
        _ = get_nearest_node(G_vehicle, delivery["coords"][0], delivery["coords"][1])
        return True
    except:
        return False

def score_vehicle_for_delivery(vehicle, delivery, warehouse_coords):
    try:
        dx = warehouse_coords[0] - delivery["coords"][0]
        dy = warehouse_coords[1] - delivery["coords"][1]
        return (dx**2 + dy**2)**0.5
    except:
        return float('inf')

def check_capacity(assignment, delivery):
    vehicle = assignment["vehicle"]
    current_weight = sum(d["delivery"].get("weight_kg", 0) for d in assignment["deliveries"])
    current_volume = sum(d["delivery"].get("volume_m3", 0) for d in assignment["deliveries"])
    max_weight = vehicle["max_weight_kg"]
    max_volume = vehicle["length_m"] * vehicle["width_m"] * vehicle["height_m"]
    dw = delivery.get("weight_kg", 0)
    dv = delivery.get("volume_m3", 0)
    return (current_weight + dw <= max_weight) and (current_volume + dv <= max_volume)

def two_opt_fixed(route, G):
    best = route
    best_cost = path_length(route, G)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                if j - i == 1:
                    continue
                new_route = best[:i] + best[i:j][::-1] + best[j:]
                new_cost = path_length(new_route, G)
                if new_cost < best_cost:
                    best = new_route
                    best_cost = new_cost
                    improved = True
    return best

def path_length(path, G):
    total_length = 0
    for i in range(len(path) - 1):
        try:
            dist = nx.shortest_path_length(G, path[i], path[i + 1], weight="length")
            total_length += dist
        except Exception:
            total_length += 9999999
    return total_length

def build_full_path_strict(G, node_sequence):
    """Strict full path: connect warehouse to reachable deliveries, skip unreachable ones individually."""
    full_path = []
    warehouse = node_sequence[0]
    deliveries = node_sequence[1:-1]
    warehouse_back = node_sequence[-1]

    current_node = warehouse
    full_path.append(current_node)

    remaining_deliveries = deliveries.copy()

    while remaining_deliveries:
        next_node = None
        best_distance = float('inf')

        for d in remaining_deliveries:
            try:
                distance = nx.shortest_path_length(G, current_node, d, weight="length")
                if distance < best_distance:
                    best_distance = distance
                    next_node = d
            except:
                continue

        if next_node is None:
            print(f"[WARNING] No more reachable deliveries from node {current_node}.")
            break  # Não consegue mais prosseguir

        try:
            path = nx.shortest_path(G, current_node, next_node, weight="length")
            full_path.extend(path[1:])  # conecta ao próximo
            current_node = next_node
            remaining_deliveries.remove(next_node)
        except:
            print(f"[WARNING] Failed to connect to delivery {next_node}. Skipping.")
            remaining_deliveries.remove(next_node)

    # Tentar voltar para o warehouse no final
    try:
        path = nx.shortest_path(G, current_node, warehouse_back, weight="length")
        full_path.extend(path[1:])
    except:
        print(f"[WARNING] Could not return to warehouse from {current_node}.")

    return full_path


def assign_clusters_heuristic(G, vehicles):
    print("\n[HEURISTIC OPTIMIZER] Starting assignment...")
    deliveries = load_json(os.path.join(CACHE_DIR, "deliveries.json"))
    deliveries_dict = {d["id"]: d for d in deliveries}
    df_debug = pd.read_csv(DEBUG_CLUSTER_CSV)
    cluster_mapping = df_debug.groupby("cluster_id")["delivery_id"].apply(list).to_dict()
    used_deliveries = set()
    assignments_final = {}
    route_id = 1
    zmrc_shape, ver_shapes, ver = prepare_restriction_shapes()
    G_vehicles = {v["license_plate"]: filter_graph_for_vehicle(G, v, zmrc_shape, ver_shapes, ver) for v in vehicles}
    for cluster_id, delivery_ids in cluster_mapping.items():
        cluster_deliveries = [deliveries_dict[did] for did in delivery_ids if did not in used_deliveries]
        if not cluster_deliveries:
            continue
        candidates = []
        for vehicle in vehicles:
            if all(can_vehicle_reach_delivery(G_vehicles[vehicle["license_plate"]], d) for d in cluster_deliveries):
                candidates.append((score_vehicle_for_delivery(vehicle, cluster_deliveries[0], WAREHOUSE_COORDS), vehicle))
        if not candidates:
            continue
        best_vehicle = sorted(candidates, key=lambda x: x[0])[0][1]
        G_vehicle = G_vehicles[best_vehicle["license_plate"]]
        delivery_nodes = []
        valid_deliveries = []
        for d in cluster_deliveries:
            try:
                node = get_nearest_node(G_vehicle, d["coords"][0], d["coords"][1])
                delivery_nodes.append(node)
                valid_deliveries.append((node, d))
                used_deliveries.add(d["id"])
            except:
                continue
        if not valid_deliveries:
            continue
        wh_node = get_nearest_node(G_vehicle, *WAREHOUSE_COORDS)
        full_path = [wh_node] + [n for n, _ in valid_deliveries] + [wh_node]
        try:
            optimized_nodes = two_opt_fixed(full_path, G_vehicle)
            full_path_validated = build_full_path_strict(G_vehicle, optimized_nodes)
            if len(set(full_path_validated)) < 2:
                raise Exception("Invalid path.")
            total_distance = sum(nx.shortest_path_length(G_vehicle, full_path_validated[i], full_path_validated[i+1], weight="length") for i in range(len(full_path_validated)-1))
            assignments_final[f"Route {route_id}"] = {
                "vehicle": best_vehicle,
                "path": full_path_validated,
                "distance_m": total_distance,
                "deliveries": [{"delivery": d, "cluster_id": cluster_id} for _, d in valid_deliveries]
            }
            print(f"[ASSIGNMENT] Vehicle {best_vehicle['license_plate']} assigned {len(valid_deliveries)} deliveries from cluster {cluster_id}.")
            route_id += 1
        except:
            for _, d in valid_deliveries:
                used_deliveries.discard(d["id"])
    print("\n[HEURISTIC OPTIMIZER] Attempting reassignment of leftovers...")
    unassigned = [d for d in deliveries if d["id"] not in used_deliveries]
    for d in unassigned:
        assigned = False
        for route_key, assignment in assignments_final.items():
            G_vehicle = G_vehicles[assignment["vehicle"]["license_plate"]]
            if can_vehicle_reach_delivery(G_vehicle, d) and check_capacity(assignment, d):
                try:
                    node = get_nearest_node(G_vehicle, d["coords"][0], d["coords"][1])
                    assignment["deliveries"].append({"delivery": d, "cluster_id": "Reassigned"})
                    print(f"[REASSIGNMENT] Delivery {d['id']} reassigned to {route_key}.")
                    assigned = True
                    break
                except:
                    continue
        if not assigned:
            print(f"[WARNING] Delivery {d['id']} could not be reassigned.")
    return assignments_final
