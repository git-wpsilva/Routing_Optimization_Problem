import json
import os


def load_json(filepath):
    """Load a JSON file and return its content."""
    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data, filepath):
    """Save a JSON object to a file."""
    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def enrich_truck_restrictions():
    """Merge restriction details from restrictions.json into truck restriction files."""
    print("Loading restriction rules...")

    # Load the restriction rules
    restrictions = load_json("data/input/restrictions/restrictions.json")

    truck_files = {
        "Caminhão 1.json": "Caminhão 1",
        "Caminhão 2.json": "Caminhão 2",
        "Caminhão 3.json": "Caminhão 3",
    }

    input_path = "data/output/"
    output_path = "data/output/enriched/"

    os.makedirs(output_path, exist_ok=True)

    for truck_file, truck_name in truck_files.items():
        print(f"Processing {truck_file}...")
        truck_data = load_json(os.path.join(input_path, truck_file))

        for feature in truck_data["features"]:
            description = feature["properties"]["Description"]

            # Rodízio Municipal (Mini Anel Viário)
            if (
                "Mini Anel" in feature["properties"]["Name"]
                or "Rodízio" in feature["properties"]["Name"]
            ):
                feature["properties"]["restriction_type"] = "Rodízio Municipal"
                feature["properties"]["restriction_times"] = restrictions[
                    "rodizio_municipal"
                ]["restriction_times"]
                feature["properties"]["plate_restrictions"] = restrictions[
                    "rodizio_municipal"
                ]["plate_restrictions"]
                feature["properties"]["exceptions"] = restrictions["rodizio_municipal"][
                    "exceptions"
                ]

            # Vias Estruturais Restritas - VER
            elif description.startswith("Via Estrutural Restrita - VER"):
                feature["properties"]["restriction_type"] = "VER"
                feature["properties"]["restriction_times"] = restrictions["ver"][
                    "restriction_times"
                ]
                feature["properties"]["exceptions"] = restrictions["ver"]["exceptions"]

                # Only Caminhão 1 has VUC restrictions
                if truck_name == "Caminhão 1":
                    feature["properties"]["vuc_restrictions"] = restrictions["ver"][
                        "vuc_restrictions"
                    ]

        # Save the enriched file
        save_json(truck_data, os.path.join(output_path, truck_file))
        print(f"Saved enriched {truck_file} to {output_path}")


def run_transformation():
    """Run the data transformation pipeline."""
    enrich_truck_restrictions()


if __name__ == "__main__":
    run_transformation()
