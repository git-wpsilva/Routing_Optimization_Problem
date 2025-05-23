import os

import geopandas as gpd
from shapely.geometry import mapping

from etl.load import load_json, save_geojson_from_features, save_json


def convert_kml_batch_if_needed(
    input_dir="data/input/restrictions", output_dir="data/output/cache"
):
    os.makedirs(output_dir, exist_ok=True)

    for filename in os.listdir(input_dir):
        if filename.endswith(".kml"):
            base_name = os.path.splitext(filename)[0].replace(" ", "_")
            output_geojson = os.path.join(
                output_dir, f"restriction_{base_name}.geojson"
            )
            input_kml = os.path.join(input_dir, filename)

            if os.path.exists(output_geojson):
                print(f"[SKIP] GeoJSON already exists: {output_geojson}")
                continue

            print(f"[CONVERT] {input_kml} → {output_geojson}")
            try:
                gdf = gpd.read_file(input_kml, driver="KML")
                gdf.to_file(output_geojson, driver="GeoJSON")
                print(f"[OK] Saved: {output_geojson}")
            except Exception as e:
                print(f"[ERROR] Failed to convert {filename}: {e}")


def enrich_zmrc_geojson():
    input_geojson = "data/output/cache/restriction_ZMRC.geojson"
    if not os.path.exists(input_geojson):
        print("[SKIP] ZMRC GeoJSON not found, skipping enrichment.")
        return

    data = load_json(input_geojson)

    if all(
        "restriction_type" in f.get("properties", {}) for f in data.get("features", [])
    ):
        print("[SKIP] Already enriched: restriction_ZMRC.geojson")
        return

    print("Enriching ZMRC GeoJSON...")

    zmrc_meta = load_json("data/input/restrictions/restrictions.json")["zmrc"]
    for feature in data["features"]:
        feature["properties"]["restriction_type"] = "ZMRC"
        feature["properties"]["restriction_times"] = zmrc_meta["restriction_times"]
        feature["properties"]["vuc_restrictions"] = zmrc_meta["vuc_restrictions"]
        feature["properties"]["vehicle_types"] = ", ".join(zmrc_meta["vehicle_types"])
        feature["properties"]["exceptions"] = ", ".join(zmrc_meta["exceptions"])

    save_json(data, input_geojson)
    print("[OK] Enriched: restriction_ZMRC.geojson")


def enrich_truck_geojson():
    print("Enriching Caminhão restriction files...")

    base_dir = "data/output/cache"
    restrictions = load_json("data/input/restrictions/restrictions.json")
    rodizio_path = os.path.join(base_dir, "restriction_Rodizio_Municipal.geojson")
    rodizio_saved = os.path.exists(rodizio_path)

    for filename in os.listdir(base_dir):
        if not filename.startswith("restriction_Caminhao") or not filename.endswith(
            ".geojson"
        ):
            continue

        file_path = os.path.join(base_dir, filename)
        data = load_json(file_path)

        if all(
            "restriction_type" in f.get("properties", {})
            for f in data.get("features", [])
        ):
            print(f"[SKIP] Already enriched: {filename}")
            continue

        enriched_features = []

        for feature in data["features"]:
            description = feature["properties"].get("Description", "")
            name = feature["properties"].get("Name", "")

            if "Mini Anel" in name or "Rodízio" in name:
                feature["properties"]["restriction_type"] = "Rodízio Municipal"
                feature["properties"]["restriction_times"] = restrictions[
                    "rodizio_municipal"
                ]["restriction_times"]
                feature["properties"]["plate_restrictions"] = restrictions[
                    "rodizio_municipal"
                ]["plate_restrictions"]
                feature["properties"]["exceptions"] = ", ".join(
                    restrictions["rodizio_municipal"]["exceptions"]
                )

                if not rodizio_saved:
                    save_geojson_from_features([feature], rodizio_path)
                    rodizio_saved = True
                    print(f"[OK] Saved Rodízio Municipal GeoJSON to {rodizio_path}")
                continue

            if description.startswith("Via Estrutural Restrita - VER"):
                feature["properties"]["restriction_type"] = "VER"
                feature["properties"]["restriction_times"] = restrictions["ver"][
                    "restriction_times"
                ]
                feature["properties"]["exceptions"] = ", ".join(
                    restrictions["ver"]["exceptions"]
                )

                if "Caminhao_1" in filename:
                    feature["properties"]["vuc_restrictions"] = restrictions["ver"][
                        "vuc_restrictions"
                    ]

            enriched_features.append(feature)

        data["features"] = enriched_features
        save_json(data, file_path)
        print(f"[OK] Enriched: {filename}")

    if not rodizio_saved:
        print(
            "[INFO] Rodízio Municipal not found in enriched caminhões — extracting from KML..."
        )
        try:
            kml_path = "data/input/restrictions/Caminhão 1.kml"
            gdf = gpd.read_file(kml_path, driver="KML")
            match = gdf[gdf["Name"] == "Mini Anel Viário - Área de Rodízio"]
            if not match.empty:
                feature = match.iloc[0]
                geojson_feature = {
                    "type": "Feature",
                    "geometry": mapping(feature.geometry),
                    "properties": {
                        "Name": feature["Name"],
                        "restriction_type": "Rodízio Municipal",
                        "restriction_times": restrictions["rodizio_municipal"][
                            "restriction_times"
                        ],
                        "plate_restrictions": restrictions["rodizio_municipal"][
                            "plate_restrictions"
                        ],
                        "exceptions": ", ".join(
                            restrictions["rodizio_municipal"]["exceptions"]
                        ),
                    },
                }
                save_geojson_from_features([geojson_feature], rodizio_path)
                print(f"[OK] Extracted Rodízio from KML and saved to {rodizio_path}")
            else:
                print("[WARN] Mini Anel Viário not found in Caminhão 1.kml")
        except Exception as e:
            print(f"[ERROR] Failed to extract Rodízio from KML: {e}")


def run_transformation():
    convert_kml_batch_if_needed()
    enrich_zmrc_geojson()
    enrich_truck_geojson()


if __name__ == "__main__":
    run_transformation()
