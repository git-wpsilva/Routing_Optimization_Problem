import os

import folium
import geopandas as gpd

from utils.config import CACHE_DIR

CLUSTER_COLORS = [
    "red",
    "blue",
    "green",
    "orange",
    "purple",
    "darkred",
    "cadetblue",
    "lightgray",
    "darkblue",
    "darkgreen",
    "pink",
    "black",
]


def plot_clusters_on_map(base_map):
    cluster_path = os.path.join(CACHE_DIR, "delivery_clusters.geojson")
    if not os.path.exists(cluster_path):
        print("[SKIP] delivery_clusters.geojson not found.")
        return base_map

    gdf = gpd.read_file(cluster_path)
    cluster_ids = gdf["cluster_id"].unique()

    for idx, cluster_id in enumerate(cluster_ids):
        color = CLUSTER_COLORS[idx % len(CLUSTER_COLORS)]
        cluster_layer = folium.FeatureGroup(name=f"Cluster {cluster_id}")

        for _, row in gdf[gdf["cluster_id"] == cluster_id].iterrows():
            geom = row.geometry
            if geom.geom_type == "Polygon":
                folium.GeoJson(
                    geom,
                    style_function=lambda f, color=color: {
                        "fillColor": color,
                        "color": color,
                        "weight": 2,
                        "fillOpacity": 0.3,
                    },
                    tooltip=f"Cluster {cluster_id}",
                ).add_to(cluster_layer)
            elif geom.geom_type == "Point":
                folium.CircleMarker(
                    location=[geom.y, geom.x],
                    radius=4,
                    color=color,
                    fill=True,
                    fill_opacity=0.8,
                    stroke=False,
                    tooltip=f"Cluster {cluster_id}",
                ).add_to(cluster_layer)

        base_map.add_child(cluster_layer)

    return base_map
