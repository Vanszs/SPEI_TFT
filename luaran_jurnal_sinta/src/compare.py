"""Bandingkan metrik TFT vs LSTM menjadi tabel siap-tempel jurnal."""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from src.config import load_config, resolve

METRICS = ["mae", "rmse", "bias", "smape_pct", "picp_80", "mpiw", "pinball"]


def compare(cfg: dict) -> pd.DataFrame:
    results_dir = resolve(cfg, cfg["paths"]["results"])
    rows = []
    for model_name in ("tft", "lstm"):
        path = results_dir / model_name / "metrics.json"
        if not path.exists():
            print(f"[skip] {path} belum ada")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        row = {"model": model_name.upper()}
        row.update({metric: payload["overall"][metric] for metric in METRICS})
        row["origins"] = payload["overall"].get("n_origins", payload["test_windows"])
        rows.append(row)

    if not rows:
        raise FileNotFoundError("Belum ada metrics.json untuk tft maupun lstm.")

    table = pd.DataFrame(rows)
    table.to_csv(results_dir / "comparison.csv", index=False)

    print("\nTabel perbandingan model")
    print(table.to_string(index=False, float_format=lambda value: f"{value:.4f}"))
    print(f"\n[ok] {results_dir / 'comparison.csv'}")
    return table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bandingkan TFT vs LSTM")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    compare(load_config(args.config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
