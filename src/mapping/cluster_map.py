import os

import fiona
import folium
import geopandas as gpd

from etl.load import save_map
from utils.config import CACHE_DIR

GPKG_PATH = os.path.join(CACHE_DIR, "delivery_clusters.gpkg")
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
    if not os.path.exists(GPKG_PATH):
        print("[WARNING] delivery_clusters.gpkg not found.")
        return base_map

    cluster_layers = fiona.listlayers(GPKG_PATH)
    color_idx = 0

    for layer_name in cluster_layers:
        gdf = gpd.read_file(GPKG_PATH, layer=layer_name)
        if gdf.empty:
            continue

        color = CLUSTER_COLORS[color_idx % len(CLUSTER_COLORS)]
        color_idx += 1

        cluster_layer = folium.FeatureGroup(name=layer_name)

        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom.geom_type == "Polygon" or geom.geom_type == "MultiPolygon":
                folium.GeoJson(
                    geom,
                    style_function=lambda f, color=color: {
                        "fillColor": color,
                        "color": color,
                        "weight": 2,
                        "fillOpacity": 0.3,
                    },
                    tooltip=layer_name,
                ).add_to(cluster_layer)
            elif geom.geom_type == "Point":
                folium.CircleMarker(
                    location=[geom.y, geom.x],
                    radius=4,
                    color=color,
                    fill=True,
                    fill_opacity=0.8,
                    stroke=False,
                    tooltip=layer_name,
                ).add_to(cluster_layer)

        base_map.add_child(cluster_layer)

    folium.LayerControl(collapsed=False).add_to(base_map)
    return base_map


if __name__ == "__main__":
    import folium

    m = folium.Map(location=[-23.5505, -46.6333], zoom_start=12)
    m = plot_clusters_on_map(m)
    save_map(m, os.path.join(CACHE_DIR, "04_clusters.html"))
    print("[MAP] Saved cluster map.")
