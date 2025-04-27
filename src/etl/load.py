import json
import os
import pickle

import pandas as pd


def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def save_geojson_from_features(features, filepath):
    geojson_data = {"type": "FeatureCollection", "features": features}
    save_json(geojson_data, filepath)


def load_pickle(filepath):
    with open(filepath, "rb") as file:
        return pickle.load(file)


def save_pickle(obj, filepath):
    with open(filepath, "wb") as file:
        pickle.dump(obj, file)


def load_csv(filepath):
    return pd.read_csv(filepath)


def save_csv(df, filepath):
    df.to_csv(filepath, index=False)


def file_exists(filepath):
    return os.path.exists(filepath)


def save_map(base_map, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    base_map.save(filepath)
    print(f"[MAP] Saved: {filepath}")
