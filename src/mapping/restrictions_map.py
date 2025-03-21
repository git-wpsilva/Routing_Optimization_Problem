import json
import os

import folium


def load_json(filepath):
    """Load a JSON file."""
    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)


def plot_restrictions(base_map):
    """Overlay restriction zones on an existing map."""
    print("Loading restriction data...")

    restriction_files = {
        "Zona do Mini Anel - Zona de Rodízio": "data/output/enriched/Caminhão 1.json",
        "Restrição 2": "data/output/enriched/Caminhão 2.json",
        "Restrição 3": "data/output/enriched/Caminhão 3.json",
    }

    # Define colors for restriction types
    restriction_colors = {"Rodízio Municipal": "red", "VER": "darkred", "VUC": "blue"}

    for layer_name, filepath in restriction_files.items():
        if not os.path.exists(filepath):
            print(f"Warning: Restriction file {filepath} not found. Skipping...")
            continue

        layer = folium.FeatureGroup(name=layer_name)
        restriction_data = load_json(filepath)

        for feature in restriction_data["features"]:
            restriction_type = feature["properties"].get("restriction_type", "Unknown")
            color = restriction_colors.get(restriction_type, "black")

            folium.GeoJson(
                feature,
                name=restriction_type,
                style_function=lambda f: {
                    "color": color,
                    "weight": 3,
                    "fillOpacity": 0.2,  # if color == "red" else 0.8,
                },
                popup=folium.Popup(
                    feature["properties"].get("Description", "No Description"),
                    max_width=300,
                ),
            ).add_to(layer)

        base_map.add_child(layer)

    return base_map  # Return the updated map to main.py
