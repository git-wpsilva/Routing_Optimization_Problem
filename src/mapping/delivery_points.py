import os
import random

import folium
from geopy.distance import geodesic

# Constants
DELIVERY_CENTER_LAT, DELIVERY_CENTER_LON = (
    -23.556664,
    -46.653497,
)  # Center of delivery radius
DELIVERY_RADIUS_KM = 15
WAREHOUSE_LAT, WAREHOUSE_LON = -23.495652, -46.655389
WAREHOUSE_OFFSET = 0.000001
WAREHOUSE_COORDS = (WAREHOUSE_LAT, WAREHOUSE_LON)
DELIVERY_CENTER_COORDS = (DELIVERY_CENTER_LAT, DELIVERY_CENTER_LON)


def generate_random_delivery_points(G, num_points=50):
    """
    Generate delivery points directly on road network nodes within radius.
    Prefer nodes not on major highways (by skipping edges tagged as motorway or trunk).
    """
    random.seed(5)
    delivery_points = []
    candidate_nodes = []

    for node, data in G.nodes(data=True):
        coord = (data["y"], data["x"])
        if geodesic(DELIVERY_CENTER_COORDS, coord).km <= DELIVERY_RADIUS_KM:
            candidate_nodes.append((node, coord))

    if len(candidate_nodes) < num_points:
        raise ValueError(
            "Not enough road nodes within delivery radius to generate delivery points."
        )

    sampled = random.sample(candidate_nodes, num_points * 2)  # Oversample
    selected = []

    for node, coord in sampled:
        # Skip if node is only connected to highway-type edges
        connected_edges = G.edges(node, data=True)
        if any(
            edge.get("highway") in ["motorway", "trunk"]
            for _, _, edge in connected_edges
        ):
            continue
        selected.append((node, coord))
        if len(selected) >= num_points:
            break

    if len(selected) < num_points:
        raise ValueError(
            "Could not find enough non-highway delivery points within radius."
        )

    delivery_points = []
    for i, (node, coord) in enumerate(selected, start=1):
        delivery = {
            "id": i,
            "coords": coord,
            "weight_kg": round(random.uniform(5, 50), 2),
            "volume_m3": round(random.uniform(0.5, 3), 3),
            "priority": random.choice(["High", "Medium", "Low"]),
            "restricted_area": random.choice(
                ["Rodízio Municipal", "ZMRC", "VER", None]
            ),
            "restriction_times": {
                "Monday": list(range(9, 17)),
                "Tuesday": list(range(9, 17)),
                "Wednesday": list(range(9, 17)),
                "Thursday": list(range(9, 17)),
                "Friday": list(range(9, 17)),
            },
        }
        delivery_points.append(delivery)

    return delivery_points


def plot_delivery_points(base_map, delivery_points):
    """Add delivery points, warehouse markers, and delivery radius to the map."""
    print("Adding delivery points...")

    delivery_points_layer = folium.FeatureGroup(name="Delivery Points")
    warehouse_layer = folium.FeatureGroup(name="Warehouse (Start/End)")
    delivery_radius_layer = folium.FeatureGroup(name="Delivery Radius")

    # Generate delivery points
    for delivery in delivery_points:
        lat, lon = delivery["coords"]
        folium.Marker(
            location=(lat, lon),
            popup=f"Delivery {delivery['id']} | Weight: {delivery['weight_kg']:.1f}kg | Volume: {delivery['volume_m3']:.2f}m³",
            tooltip=f"Lat: {lat:.5f}, Lon: {lon:.5f}",
            icon=folium.Icon(color="green", icon="shopping-cart", prefix="fa"),
        ).add_to(delivery_points_layer)

    # Add delivery radius circle
    folium.Circle(
        location=DELIVERY_CENTER_COORDS,
        radius=DELIVERY_RADIUS_KM * 1000,  # in meters
        color="green",
        fill=True,
        fill_opacity=0.05,
        popup="Delivery Radius",
    ).add_to(delivery_radius_layer)

    # Add warehouse start and end markers
    folium.Marker(
        location=(WAREHOUSE_LAT, WAREHOUSE_LON),
        popup="Warehouse Start",
        icon=folium.Icon(color="blue", icon="play", prefix="fa"),
    ).add_to(warehouse_layer)

    folium.Marker(
        location=(WAREHOUSE_LAT + WAREHOUSE_OFFSET, WAREHOUSE_LON + WAREHOUSE_OFFSET),
        popup="Warehouse End",
        icon=folium.Icon(color="red", icon="stop", prefix="fa"),
    ).add_to(warehouse_layer)

    # Add all layers
    delivery_radius_layer.add_to(base_map)
    delivery_points_layer.add_to(base_map)
    warehouse_layer.add_to(base_map)

    return base_map


def plot_warehouse(base_map, warehouse_coords, popup="Warehouse"):
    """Add the warehouse location as a green marker to the map."""
    folium.Marker(
        location=warehouse_coords,
        popup=popup,
        icon=folium.Icon(color="green", icon="home", prefix="fa"),
    ).add_to(base_map)
    return base_map


def plot_route(base_map, G, path_nodes, license_plate, route_id):
    """Load route from saved geojson and add to map."""
    geojson_path = f"data/output/routes_geojson/route_{route_id}.geojson"
    if not os.path.exists(geojson_path):
        print(f"[WARNING] GeoJSON not found for Route {route_id}")
        return base_map

    with open(geojson_path, "r") as f:
        geojson_data = f.read()

    layer = folium.GeoJson(
        geojson_data,
        name=f"Route {route_id}",
        tooltip=folium.Tooltip(f"Route {route_id} | Plate: {license_plate}"),
    )
    layer.add_to(base_map)

    return base_map
