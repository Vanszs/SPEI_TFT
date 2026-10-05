import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.preprocess import (  # noqa: E402
    DEFAULT_TOP_K,
    SELECTION_END_DATE,
    WEATHER_COLS,
    _compute_similarity,
    _interpolate_per_node,
    _select_top_k_nodes,
    _validate_raw_schema,
)

RAW_PATH = ROOT / "data/raw/weather_history_east_java.parquet"
OUTPUT_PATH = ROOT / "results/bab3_node_weight_sensitivity.json"
SCENARIOS = {
    "S1": (0.5, 0.5),
    "S2": (0.6, 0.4),
    "S3": (0.7, 0.3),
    "S4": (0.8, 0.2),
    "S5": (1.0, 0.0),
}
REFERENCE_SCENARIO = "S3"


def _load_train_slice():
    if not RAW_PATH.exists():
        raise FileNotFoundError(f"Raw data not found at {RAW_PATH}")

    df = pd.read_parquet(RAW_PATH)
    df["time"] = pd.to_datetime(df["time"])
    _validate_raw_schema(df)
    df = df.sort_values(["city_id", "raw_node_id", "time"]).reset_index(drop=True)

    duplicate_raw = df.duplicated(subset=["raw_node_id", "time"]).sum()
    if duplicate_raw:
        raise ValueError(f"Duplicate (raw_node_id,time) rows found: {duplicate_raw}")
    if df.duplicated(subset=["node_id", "time"]).sum():
        raise ValueError("Duplicate (node_id,time) rows found in raw data.")
    if df[["node_id"]].drop_duplicates()["node_id"].duplicated().any():
        raise ValueError("node_id must be globally unique.")

    df = _interpolate_per_node(df)
    cutoff = pd.Timestamp(SELECTION_END_DATE)
    train_slice = df[df["time"] <= cutoff].copy()
    if train_slice.empty:
        raise ValueError("Train-only slice for node selection is empty.")
    if train_slice["time"].max() > cutoff:
        raise ValueError("Train slice exceeds selection_end_date boundary.")
    return train_slice


def _select_for_weights(similarity_df, behavior_weight, distance_weight):
    weighted = similarity_df.copy()
    weighted["hybrid_score"] = (
        behavior_weight * weighted["behavior_score"]
        + distance_weight * weighted["distance_score"]
    )
    return _select_top_k_nodes(weighted, top_k=DEFAULT_TOP_K)


def _top5_by_city(selected_nodes):
    return {
        str(city_id): group.sort_values("selected_rank")["raw_node_id"].tolist()
        for city_id, group in selected_nodes.groupby("city_id", sort=True)
    }


def _stability_vs_reference(selected_by_city, reference_by_city):
    per_city = {
        city_id: len(set(nodes).intersection(reference_by_city[city_id]))
        for city_id, nodes in selected_by_city.items()
    }
    return {"per_city": per_city, "total": int(sum(per_city.values()))}


def _pearson(a, b):
    if len(a) < 10 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _mean_representativeness(df_train, selected_by_city):
    correlations = []
    for city_id, selected_nodes in selected_by_city.items():
        city_df = df_train[df_train["city_id"] == city_id]
        selected_df = city_df[city_df["raw_node_id"].isin(selected_nodes)]
        leave_one_out_df = city_df[~city_df["raw_node_id"].isin(selected_nodes)]
        selected_profile = selected_df.groupby("time")[WEATHER_COLS].mean().sort_index()
        leave_one_out_profile = (
            leave_one_out_df.groupby("time")[WEATHER_COLS].mean().sort_index()
        )
        aligned = selected_profile.join(
            leave_one_out_profile,
            how="inner",
            lsuffix="_selected",
            rsuffix="_leave_one_out",
        ).dropna()
        for col in WEATHER_COLS:
            correlation = _pearson(
                aligned[f"{col}_selected"].to_numpy(),
                aligned[f"{col}_leave_one_out"].to_numpy(),
            )
            if correlation is not None:
                correlations.append(correlation)
    if not correlations:
        return None
    return float(np.mean(correlations))


def main():
    df_train = _load_train_slice()
    similarity_df = _compute_similarity(df_train)

    selected_by_scenario = {}
    for scenario, (behavior_weight, distance_weight) in SCENARIOS.items():
        selected = _select_for_weights(
            similarity_df, behavior_weight, distance_weight
        )
        selected_by_scenario[scenario] = _top5_by_city(selected)

    reference = selected_by_scenario[REFERENCE_SCENARIO]
    results = {}
    for scenario, (behavior_weight, distance_weight) in SCENARIOS.items():
        top5 = selected_by_scenario[scenario]
        results[scenario] = {
            "weights": {
                "behavior": behavior_weight,
                "distance": distance_weight,
            },
            "per_city_top5": top5,
            "stability_vs_ref": _stability_vs_reference(top5, reference),
            "mean_representativeness": _mean_representativeness(df_train, top5),
        }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2)
        file.write("\n")

    print("scenario  behavior  distance  stability_total  mean_representativeness")
    for scenario, result in results.items():
        weights = result["weights"]
        print(
            f"{scenario:<8} {weights['behavior']:<9.1f} {weights['distance']:<9.1f} "
            f"{result['stability_vs_ref']['total']:<17} "
            f"{result['mean_representativeness']:.6f}"
        )
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
