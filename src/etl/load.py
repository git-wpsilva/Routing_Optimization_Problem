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


def load_geojson(filepath):
    return load_json(filepath)


def save_geojson(data, filepath):
    save_json(data, filepath)


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
