import math
import random

import folium
from geopy.distance import geodesic

# Constants
START_LAT, START_LON = -23.556664, -46.653497
DELIVERY_RADIUS_KM = 15
WAREHOUSE_LAT, WAREHOUSE_LON = -23.495652, -46.655389
WAREHOUSE_OFFSET = 0.000001


def generate_random_delivery_points(num_points):
    """Generate random delivery points with realistic e-commerce weights."""
    delivery_points = []
    for _ in range(num_points):
        while True:
            bearing = random.uniform(0, 360)
            distance = random.uniform(0, DELIVERY_RADIUS_KM)
            bearing_rad = math.radians(bearing)
            lat_offset = distance * math.cos(bearing_rad) / 111
            lon_offset = (
                distance
                * math.sin(bearing_rad)
                / (111 * math.cos(math.radians(START_LAT)))
            )

            new_lat, new_lon = START_LAT + lat_offset, START_LON + lon_offset

            if (
                geodesic((START_LAT, START_LON), (new_lat, new_lon)).km
                <= DELIVERY_RADIUS_KM
            ):
                delivery = {
                    "coords": (new_lat, new_lon),
                    "weight_kg": random.uniform(
                        1, 30
                    ),  # ✅ E-commerce realistic weight (1kg - 30kg)
                    "volume_m3": random.uniform(
                        0.01, 0.2
                    ),  # ✅ Small packages (0.01m³ - 0.2m³)
                    "priority": random.choice(["High", "Medium", "Low"]),
                }
                delivery_points.append(delivery)
                break
    return delivery_points


def plot_delivery_points(base_map, num_points=10):
    """Add delivery points & warehouse to an existing map."""
    print(f"Adding {num_points} delivery points...")

    delivery_points_layer = folium.FeatureGroup(name="Delivery Points")
    warehouse_layer = folium.FeatureGroup(name="Warehouse (Start/End)")

    # Generate delivery points
    delivery_points = generate_random_delivery_points(num_points)
    for idx, delivery in enumerate(delivery_points):
        lat, lon = delivery["coords"]  # ✅ Fix: Extract lat, lon from dictionary

        folium.Marker(
            location=(lat, lon),
            popup=f"Delivery {idx + 1} | Weight: {delivery['weight_kg']:.1f}kg | Volume: {delivery['volume_m3']:.2f}m³",
            tooltip=f"Lat: {lat:.5f}, Lon: {lon:.5f}",
            icon=folium.Icon(color="green", icon="shopping-cart", prefix="fa"),
        ).add_to(delivery_points_layer)

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

    # Add layers to the map
    base_map.add_child(delivery_points_layer)
    base_map.add_child(warehouse_layer)

    return base_map  # Return updated map
