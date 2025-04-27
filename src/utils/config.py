# === Delivery Schedule ===
DELIVERY_DAY = "Tuesday"
DELIVERY_HOUR = 10
HOLIDAY = False

# === Delivery Constraints ===
MAX_ROUTE_DISTANCE_KM = 1000
MAX_ROUTE_DURATION_HOURS = 5
MAX_STOPS_PER_ROUTE = 25
MAX_DISTANCE_TO_ROAD_METERS = 1000
ASSUME_SPEED_KMPH = 30

# Center of delivery radius
DELIVERY_CENTER_LAT = -23.556664
DELIVERY_CENTER_LON = -46.653497
DELIVERY_RADIUS_KM = 15
WAREHOUSE_LAT = -23.495652
WAREHOUSE_LON = -46.655389
WAREHOUSE_OFFSET = 0.000001
WAREHOUSE_COORDS = (WAREHOUSE_LAT, WAREHOUSE_LON)
DELIVERY_CENTER_COORDS = (DELIVERY_CENTER_LAT, DELIVERY_CENTER_LON)


# === File Paths ===
# Input
VEHICLE_FLEET_FILE = "data/input/vehicle_fleet.json"
RESTRICTIONS_FILE = "data/input/restrictions/restrictions.json"

# Output - Cache and Artifacts
ROAD_NETWORK_FILE = "data/output/road_network.pkl"
RESTRICTION_INDEX_FILE = "data/output/cache/restriction_data.json"
CACHE_DIR = "data/output/cache"

# GeoJSON Exports
ROUTES_GEOJSON_DIR = "data/output/routes_geojson"
EXPORT_PATH = "data/output/map_data_export.json"

# Mapping
MAPS_DIR = "data/output/maps"
STEPS_DIR = "data/output/maps/steps"
FINAL_MAP_PATH = "data/output/maps/route_plan_map.html"

# Debug
DEBUG_ROUTE_PATH = "data/output/debug_routes.csv"

# Warehouse (Fixed Reference Point)
WAREHOUSE_COORDS = (-23.495652, -46.655389)


IGNORE_RESTRICTIONS = False
