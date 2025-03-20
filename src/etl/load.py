import json
import folium
import os

def load_json(filepath):
    """Load a JSON file and return its content."""
    with open(filepath, 'r', encoding='utf-8') as file:
        return json.load(file)

def generate_map():
    """Load restriction data and generate a Folium map with layers."""
    print("Loading enriched restriction data...")

    # Load enriched restriction files
    restriction_files = {
        "Restrição 1": "data/output/enriched/Caminhão 1.json",
        "Restrição 2": "data/output/enriched/Caminhão 2.json",
        "Restrição 3": "data/output/enriched/Caminhão 3.json"
    }
    
    # Initialize the map centered in São Paulo
    sao_paulo_map = folium.Map(location=[-23.5505, -46.6333], zoom_start=12)

    # Define colors for different restriction types
    restriction_colors = {
        "Rodízio Municipal": "red",
        "VER": "darkred",
        "VUC": "blue"
    }

    for layer_name, filepath in restriction_files.items():
        restriction_layer = folium.FeatureGroup(name=layer_name)
        restriction_data = load_json(filepath)

        for feature in restriction_data["features"]:
            restriction_type = feature["properties"].get("restriction_type", "Unknown")
            color = restriction_colors.get(restriction_type, "black")

            folium.GeoJson(
                feature,
                name=restriction_type,
                style_function=lambda f: {
                    "color": color,
                    "weight": 3 if color == "darkred" else 2,
                    "fillOpacity": 0.2 if color == "red" else 0.8
                },
                tooltip=folium.Tooltip(feature["properties"].get("Name", "Unknown Road")),
                popup=folium.Popup(feature["properties"].get("Description", "No Description"), max_width=300)
            ).add_to(restriction_layer)

        sao_paulo_map.add_child(restriction_layer)

    folium.LayerControl(collapsed=False).add_to(sao_paulo_map)

    output_path = "data/output/maps/route_plan_map.html"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sao_paulo_map.save(output_path)
    print(f"Map successfully saved to: {output_path}")

def run_pipeline():
    """Execute the full data loading and visualization process."""
    generate_map()

if __name__ == "__main__":
    run_pipeline()
