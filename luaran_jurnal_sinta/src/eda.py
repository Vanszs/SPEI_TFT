"""EDA ringkas untuk bagian Hasil: seri waktu, siklus musiman, distribusi target."""

from __future__ import annotations

import argparse
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.config import load_config, resolve, target_label


def _shade_splits(ax, frame: pd.DataFrame) -> None:
    colors = {"train": "#e5e7eb", "val": "#fde68a", "test": "#fecaca"}
    for split, group in frame.groupby("split"):
        ax.axvspan(group.index.min(), group.index.max(), color=colors[split], alpha=0.45, lw=0)


def eda(cfg: dict) -> None:
    data_path = resolve(cfg, cfg["data"]["processed_dir"]) / "bromo_daily.parquet"
    frame = pd.read_parquet(data_path)
    target = cfg["data"]["target"]
    label = target_label(cfg)
    output_dir = resolve(cfg, cfg["paths"]["results"]) / "eda"
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(frame.index, frame[target], color="#1f2937", lw=1)
    _shade_splits(ax, frame)
    ax.set_ylabel(f"{label} (C)")
    ax.set_title(f"Seri harian {cfg['study']['name']} ({frame.index.min().date()} - {frame.index.max().date()})")
    fig.tight_layout()
    fig.savefig(output_dir / "timeseries.png", dpi=180)
    plt.close(fig)

    monthly = frame.groupby(frame.index.month)[target].agg(["mean", "min", "max"])
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(monthly.index, monthly["mean"], marker="o", color="#b91c1c", label="Rata-rata")
    ax.fill_between(monthly.index, monthly["min"], monthly["max"], color="#ef4444", alpha=0.15,
                    label="Min-max")
    ax.set_xticks(range(1, 13))
    ax.set_xlabel("Bulan")
    ax.set_ylabel(f"{label} (C)")
    ax.set_title(f"Siklus musiman {label.lower()}")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_dir / "seasonal_cycle.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.hist(frame[target], bins=40, color="#1f2937", alpha=0.85)
    ax.axvline(frame[target].mean(), color="#b91c1c", ls="--", lw=1, label="Mean")
    ax.set_xlabel(f"{label} (C)")
    ax.set_ylabel("Frekuensi")
    ax.set_title(f"Distribusi {label.lower()} harian")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_dir / "distribution.png", dpi=180)
    plt.close(fig)

    summary = frame.groupby("split")[target].agg(["count", "mean", "std", "min", "max"])
    summary.to_csv(output_dir / "target_by_split.csv")
    print(summary.to_string())
    print(f"[ok] artefak EDA: {output_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EDA target Bromo")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    eda(load_config(args.config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
