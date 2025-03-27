import random
import folium
from geopy.distance import geodesic

# Constants
DELIVERY_CENTER_LAT, DELIVERY_CENTER_LON = -23.556664, -46.653497  # Center of delivery radius
DELIVERY_RADIUS_KM = 15
WAREHOUSE_LAT, WAREHOUSE_LON = -23.495652, -46.655389
WAREHOUSE_OFFSET = 0.000001
WAREHOUSE_COORDS = (WAREHOUSE_LAT, WAREHOUSE_LON)
DELIVERY_CENTER_COORDS = (DELIVERY_CENTER_LAT, DELIVERY_CENTER_LON)


def generate_random_delivery_points(num_points=10):
    """
    Generate random delivery points within DELIVERY_RADIUS_KM of the delivery center.
    Adds unique IDs and synthetic restrictions to each delivery point.
    """
    random.seed(10)
    delivery_points = []

    while len(delivery_points) < num_points:
        lat = random.uniform(DELIVERY_CENTER_LAT - 0.15, DELIVERY_CENTER_LAT + 0.15)
        lon = random.uniform(DELIVERY_CENTER_LON - 0.15, DELIVERY_CENTER_LON + 0.15)
        if geodesic(DELIVERY_CENTER_COORDS, (lat, lon)).km > DELIVERY_RADIUS_KM:
            continue

        delivery = {
            "id": len(delivery_points) + 1,
            "coords": (lat, lon),
            "weight_kg": round(random.uniform(5, 50), 2),
            "volume_m3": round(random.uniform(0.05, 0.3), 3),
            "priority": random.choice(["High", "Medium", "Low"]),
            "restricted_area": random.choice(["Rodízio Municipal", "ZMRC", "VER", None]),
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
        popup="Delivery Radius"
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