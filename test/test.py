import fiona

ROUTES_GPKG_PATH = "data/output/cache/routes.gpkg"



print("\n[DEBUG] Camadas disponíveis no GPKG:")
for layer_name in fiona.listlayers(ROUTES_GPKG_PATH):
    print("-", layer_name)
