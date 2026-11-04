"""Add rolling-origin forecast history to the published forecast artifact."""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

DEFAULT_ARTIFACT = Path("frontend/public/forecast_30d.json")


def atomic_write_json(path, payload) -> None:
    """Tulis artefak lewat file sementara + rename, agar pembaca tidak pernah
    melihat JSON setengah jadi bila proses mati di tengah penulisan."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    tmp.replace(path)


def build_history(artifact: str | Path = DEFAULT_ARTIFACT, windows: int = 3, days: int = 30) -> None:
    path = Path(artifact)
    payload = json.loads(path.read_text(encoding="utf-8"))
    import torch

    torch.set_float32_matmul_precision("medium")
    from src.evaluation.inference import build_bundle

    bundle = build_bundle()
    print("checkpoint:", bundle.checkpoint_path, flush=True)
    print("last_observed:", bundle.last_observed_time.date(), flush=True)
    payload["schema_version"] = 2
    payload["history_windows"] = windows
    payload["history_days"] = days

    cutoff = pd.Timestamp(payload.get("last_observed") or payload["cities"][next(iter(payload["cities"]))]["forecast"]["dates"][0])
    for city in payload["cities"]:
        current = payload["cities"][city]["forecast"].get("dates", [])
        current_start = date.fromisoformat(current[0]) if current else bundle.last_observed_time.date() + timedelta(days=1)
        entity = bundle._entity_for(city)
        city_rows = bundle.data[
            (bundle.data["super_node_id"].astype(str) == entity)
            & (pd.to_datetime(bundle.data["time"]) <= cutoff)
        ]
        actuals = city_rows.set_index(pd.to_datetime(city_rows["time"]).dt.date)["SPEI_3"]
        history = []
        for k in range(windows, 0, -1):
            window_start = current_start - timedelta(days=k * days)
            as_of = window_start - timedelta(days=1)
            result = bundle.forecast_as_of(city, as_of, days)
            dates = result["dates"]
            history.append({
                "as_of": as_of.isoformat(),
                "dates": dates,
                "p10": [round(v, 4) for v in result["p10"]],
                "p50": [round(v, 4) for v in result["p50"]],
                "p90": [round(v, 4) for v in result["p90"]],
                "actual": [None if pd.isna(actuals.get(date.fromisoformat(d))) else round(float(actuals[date.fromisoformat(d)]), 4) for d in dates],
            })
        payload["cities"][city]["history"] = history

    atomic_write_json(path, payload)
    print(f"written: {path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build rolling-origin forecast history")
    parser.add_argument("--artifact", default=str(DEFAULT_ARTIFACT))
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.windows < 1 or args.days < 1:
        parser.error("--windows and --days must be positive")
    if args.dry_run:
        payload = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
        last = date.fromisoformat(payload["last_observed"])
        for city in payload["cities"]:
            dates = payload["cities"][city]["forecast"].get("dates", [])
            current_start = date.fromisoformat(dates[0]) if dates else last + timedelta(days=1)
            for k in range(args.windows, 0, -1):
                start = current_start - timedelta(days=k * args.days)
                print(f"{city}: as_of={(start - timedelta(days=1)).isoformat()} origin={start.isoformat()}")
        return
    build_history(args.artifact, args.windows, args.days)


if __name__ == "__main__":
    main()
