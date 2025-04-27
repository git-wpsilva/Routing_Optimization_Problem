import csv
import os

import geopandas as gpd
import numpy as np
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from sklearn.metrics import pairwise_distances

from etl.load import load_json
from utils.config import CACHE_DIR

BUFFER_RADIUS = 0.02
MERGE_DISTANCE = 0.05
MAX_CLUSTERS = 6
CLUSTER_SIZE_THRESHOLD_RATIO = 0.08
MERGE_DISTANCE_THRESHOLD = 0.04
GPKG_PATH = os.path.join(CACHE_DIR, "delivery_clusters.gpkg")


def detect_zone(point, zmrc_shape, rodizio_shape):
    if zmrc_shape.contains(point):
        return "ZMRC"
    elif rodizio_shape.contains(point):
        return "Rodizio"
    else:
        return None


def merge_close_buffers(buffers_gdf, distance_threshold):
    coords = np.array(
        [[geom.centroid.x, geom.centroid.y] for geom in buffers_gdf.geometry]
    )
    dist_matrix = pairwise_distances(coords)
    n = len(coords)
    clusters = []
    assigned = [-1] * n
    cluster_id = 1

    for i in range(n):
        if assigned[i] != -1:
            continue
        group = [i]
        assigned[i] = cluster_id
        for j in range(i + 1, n):
            if dist_matrix[i][j] < distance_threshold:
                assigned[j] = cluster_id
                group.append(j)
        cluster_geom = unary_union([buffers_gdf.geometry[k] for k in group])
        clusters.append((f"Cluster {cluster_id}", cluster_geom, group))
        cluster_id += 1

    return clusters


def generate_delivery_clusters():
    if os.path.exists(GPKG_PATH):
        os.remove(GPKG_PATH)

    path_zmrc = os.path.join(CACHE_DIR, "restriction_ZMRC.geojson")
    path_rodizio = os.path.join(CACHE_DIR, "restriction_Rodizio_Municipal.geojson")
    zmrc_shape = shape(gpd.read_file(path_zmrc).geometry.iloc[0]).buffer(0)
    rodizio_shape = shape(gpd.read_file(path_rodizio).geometry.iloc[0]).buffer(0)

    deliveries = load_json(os.path.join(CACHE_DIR, "deliveries.json"))

    delivery_points = []
    id_map = {}
    for idx, d in enumerate(deliveries, start=1):
        if "coords" in d and len(d["coords"]) == 2:
            point = Point(d["coords"][1], d["coords"][0])
            delivery_points.append((idx, point))
            id_map[idx] = point

    inside_zmrc, inside_rodizio, outside = [], [], []
    for idx, point in delivery_points:
        zone = detect_zone(point, zmrc_shape, rodizio_shape)
        if zone == "ZMRC":
            inside_zmrc.append((idx, point))
        elif zone == "Rodizio":
            inside_rodizio.append((idx, point))
        else:
            outside.append((idx, point))

    cluster_members = {}
    debug_data = []

    total_deliveries = len(delivery_points)
    min_points_per_cluster = max(
        3, int(total_deliveries * CLUSTER_SIZE_THRESHOLD_RATIO)
    )

    if outside:
        buffer_gdf = gpd.GeoDataFrame(
            geometry=[p.buffer(BUFFER_RADIUS) for idx, p in outside], crs="EPSG:4326"
        )
        merged = merge_close_buffers(buffer_gdf, MERGE_DISTANCE)

        for cluster_id, geom, group in merged:
            member_ids = [outside[idx][0] for idx in group]
            cluster_members[cluster_id] = {
                "geometry": geom,
                "members": member_ids,
                "requires_zmrc": False,
                "requires_rodizio": False,
            }

    all_clusters = dict(cluster_members)

    # Handle ZMRC region
    if len(inside_zmrc) >= min_points_per_cluster:
        all_clusters["ZMRC"] = {
            "geometry": zmrc_shape,
            "members": [idx for idx, _ in inside_zmrc],
            "requires_zmrc": True,
            "requires_rodizio": False,
        }
    else:
        for idx, point in inside_zmrc:
            candidates = [(cid, data) for cid, data in cluster_members.items()]
            p = id_map[idx]
            nearest = min(
                candidates, key=lambda x: p.distance(x[1]["geometry"].centroid)
            )
            cid = nearest[0]
            cluster_members[cid]["geometry"] = unary_union(
                [cluster_members[cid]["geometry"], p.buffer(BUFFER_RADIUS)]
            )
            cluster_members[cid]["members"].append(idx)
            cluster_members[cid]["requires_zmrc"] = True

    # Handle Rodizio region
    if len(inside_rodizio) >= min_points_per_cluster:
        all_clusters["Rodizio"] = {
            "geometry": rodizio_shape,
            "members": [idx for idx, _ in inside_rodizio],
            "requires_zmrc": False,
            "requires_rodizio": True,
        }
    else:
        for idx, point in inside_rodizio:
            candidates = [(cid, data) for cid, data in cluster_members.items()]
            p = id_map[idx]
            nearest = min(
                candidates, key=lambda x: p.distance(x[1]["geometry"].centroid)
            )
            cid = nearest[0]
            cluster_members[cid]["geometry"] = unary_union(
                [cluster_members[cid]["geometry"], p.buffer(BUFFER_RADIUS)]
            )
            cluster_members[cid]["members"].append(idx)
            cluster_members[cid]["requires_rodizio"] = True

    # Force merging of small clusters
    def force_merge_clusters(clusters):
        changed = True
        while changed:
            changed = False
            small_clusters = [
                cid
                for cid, data in clusters.items()
                if len(data["members"]) < min_points_per_cluster
            ]
            if not small_clusters:
                break
            for cid in small_clusters:
                candidates = [(k, v) for k, v in clusters.items() if k != cid]
                if not candidates:
                    continue
                target_id, target_data = min(
                    candidates,
                    key=lambda x: clusters[cid]["geometry"].centroid.distance(
                        x[1]["geometry"].centroid
                    ),
                )
                clusters[target_id]["geometry"] = unary_union(
                    [clusters[target_id]["geometry"], clusters[cid]["geometry"]]
                )
                clusters[target_id]["members"].extend(clusters[cid]["members"])
                clusters[target_id]["requires_zmrc"] |= clusters[cid]["requires_zmrc"]
                clusters[target_id]["requires_rodizio"] |= clusters[cid][
                    "requires_rodizio"
                ]
                del clusters[cid]
                changed = True
                break
        return clusters

    all_clusters = force_merge_clusters(all_clusters)

    used_ids = set()
    for cluster_id, data in all_clusters.items():
        data["members"] = list(set(data["members"]))
        for idx in data["members"]:
            if idx not in used_ids:
                debug_data.append({"delivery_id": idx, "cluster_id": cluster_id})
                used_ids.add(idx)

    # Export to GeoPackage
    for cluster_id, data in all_clusters.items():
        gdf = gpd.GeoDataFrame(
            [
                {
                    "geometry": data["geometry"],
                    "cluster_id": cluster_id,
                    "requires_zmrc": data.get("requires_zmrc", False),
                    "requires_rodizio": data.get("requires_rodizio", False),
                }
            ],
            crs="EPSG:4326",
        )
        gdf.to_file(GPKG_PATH, layer=f"cluster_{cluster_id}", driver="GPKG")

    debug_path = os.path.join(CACHE_DIR, "cluster_debug.csv")
    with open(debug_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["delivery_id", "cluster_id"])
        writer.writeheader()
        for row in debug_data:
            writer.writerow(row)

    print(f"[CLUSTERS] Saved to single GeoPackage: {GPKG_PATH}")
    print(f"[DEBUG] Saved: {debug_path}")


if __name__ == "__main__":
    generate_delivery_clusters()
