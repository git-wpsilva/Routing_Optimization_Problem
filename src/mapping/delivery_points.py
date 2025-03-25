import random

import folium

# Constants
START_LAT, START_LON = -23.556664, -46.653497
DELIVERY_RADIUS_KM = 15
WAREHOUSE_LAT, WAREHOUSE_LON = -23.495652, -46.655389
WAREHOUSE_OFFSET = 0.000001


def generate_random_delivery_points(num_points=10):
    """
    Generate random delivery points across a defined bounding box (São Paulo region).
    Adds unique IDs and synthetic restrictions to each delivery point.
    """
    random.seed(10)
    delivery_points = []
    lat_range = (-23.7, -23.4)
    lon_range = (-46.85, -46.4)

    for i in range(1, num_points + 1):
        lat = random.uniform(*lat_range)
        lon = random.uniform(*lon_range)

        delivery = {
            "id": i,
            "coords": (lat, lon),
            "weight_kg": round(random.uniform(5, 50), 2),
            "volume_m3": round(random.uniform(0.05, 0.3), 3),
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
    """Add delivery points & warehouse to an existing map."""
    print("Adding delivery points...")

    delivery_points_layer = folium.FeatureGroup(name="Delivery Points")
    warehouse_layer = folium.FeatureGroup(name="Warehouse (Start/End)")

    # Generate delivery points
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


def plot_warehouse(base_map, warehouse_coords, popup="Warehouse"):
    """Add the warehouse location as a green marker to the map."""
    folium.Marker(
        location=warehouse_coords,
        popup=popup,
        icon=folium.Icon(color="green", icon="home", prefix="fa"),
    ).add_to(base_map)
    return base_map
