import pickle

with open("data/output/road_network.pkl", "rb") as f:
    G = pickle.load(f)

print("Tipo de G:", type(G))
print("Tem atributo `.graph`?", hasattr(G, "graph"))

