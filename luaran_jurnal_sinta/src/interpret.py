"""Ekstrak interpretability bawaan TFT: variable importance + temporal attention."""

from __future__ import annotations

import argparse
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pytorch_forecasting import TimeSeriesDataSet

from src.config import load_config, resolve
from src.dataset import dataloader, split_frame
from src.evaluate import resolve_checkpoint
from src.models import load_checkpoint


def interpret(cfg: dict, checkpoint: str | None = None) -> None:
    data = pd.read_parquet(resolve(cfg, cfg["data"]["processed_dir"]) / "bromo_daily.parquet")
    checkpoint_path = resolve_checkpoint(cfg, "tft", checkpoint)
    model = load_checkpoint("tft", str(checkpoint_path), map_location="cpu")
    model.eval()

    encoder_length = int(model.dataset_parameters["max_encoder_length"])
    frame = split_frame(data, "test", encoder_length)
    test_dataset = TimeSeriesDataSet.from_parameters(
        model.dataset_parameters,
        frame,
        predict=False,
        stop_randomization=True,
    )
    loader = dataloader(test_dataset, cfg, train=False)

    raw = model.predict(
        loader,
        mode="raw",
        return_x=True,
        trainer_kwargs={"logger": False},
    )
    interpretation = model.interpret_output(raw.output, reduction="sum")

    results_dir = resolve(cfg, cfg["paths"]["results"]) / "tft" / "interpretation"
    results_dir.mkdir(parents=True, exist_ok=True)

    names = list(model.encoder_variables)
    weights = interpretation["encoder_variables"].detach().cpu().numpy().ravel()
    if len(names) != weights.size:
        raise ValueError(f"Jumlah nama variabel ({len(names)}) != bobot ({weights.size}).")
    weights = weights / (weights.sum() + 1e-12)
    importance = pd.DataFrame({"variable": names, "importance_pct": weights * 100.0})
    importance.sort_values("importance_pct", ascending=False).to_csv(
        results_dir / "encoder_variable_importance.csv", index=False
    )

    attention = interpretation["attention"].detach().cpu().numpy().ravel()
    relative_time = np.arange(-encoder_length, -encoder_length + len(attention))
    pd.DataFrame({"relative_day": relative_time, "attention": attention}).to_csv(
        results_dir / "temporal_attention.csv", index=False
    )

    figs = model.plot_interpretation(interpretation)
    for name, figure in figs.items():
        if not figure.axes or not figure.axes[0].has_data():
            plt.close(figure)
            continue
        path = results_dir / f"{name}.png"
        figure.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(figure)
        print(f"[ok] {path}")

    print("\nEncoder variable importance:")
    print(importance.sort_values("importance_pct", ascending=False).to_string(index=False))
    print(f"\n[ok] artefak interpretasi: {results_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interpretability TFT Bromo")
    parser.add_argument("--config", default=None)
    parser.add_argument("--checkpoint", default=None)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    interpret(cfg, checkpoint=args.checkpoint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
