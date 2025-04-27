import os

import folium

from etl.load import load_json
from utils.config import CACHE_DIR

RESTRICTION_COLOR_MAP = {
    "Rodízio Municipal": "red",
    "VER": "darkred",
    "ZMRC": "blue",
    "VUC": "green",
}


def plot_restrictions(base_map):
    print("Loading restriction data...")

    for filename in os.listdir(CACHE_DIR):
        if not filename.startswith("restriction_") or not filename.endswith(".geojson"):
            continue

        filepath = os.path.join(CACHE_DIR, filename)
        try:
            data = load_json(filepath)
        except Exception as e:
            print(f"[ERROR] Failed to load {filename}: {e}")
            continue

        layer_name = (
            filename.replace("restriction_", "")
            .replace(".geojson", "")
            .replace("_", " ")
            .title()
        )
        restriction_layer = folium.FeatureGroup(name=layer_name)

        for feature in data.get("features", []):
            restriction_type = feature.get("properties", {}).get(
                "restriction_type", layer_name
            )
            color = RESTRICTION_COLOR_MAP.get(restriction_type, "gray")

            folium.GeoJson(
                feature,
                name=restriction_type,
                style_function=lambda f, color=color: {
                    "color": color,
                    "weight": 2,
                    "fillOpacity": 0.3 if color != "gray" else 0.1,
                },
                tooltip=folium.Tooltip(
                    feature.get("properties", {}).get("Name", "Unknown")
                ),
                popup=folium.Popup(
                    feature.get("properties", {}).get("Description", "No description"),
                    max_width=300,
                ),
            ).add_to(restriction_layer)

        base_map.add_child(restriction_layer)

    return base_map
