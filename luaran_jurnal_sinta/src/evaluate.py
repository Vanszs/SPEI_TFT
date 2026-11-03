"""Evaluasi kuantitatif TFT/LSTM pada split test + artefak untuk naskah jurnal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pytorch_forecasting import TimeSeriesDataSet

from src.config import load_config, resolve, target_label
from src.dataset import dataloader, split_frame
from src.models import load_checkpoint


def resolve_checkpoint(cfg: dict, model_name: str, explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    logs_dir = resolve(cfg, cfg["paths"]["logs"])
    run_config = logs_dir / f"run_config_{model_name}.json"
    if run_config.exists():
        data = json.loads(run_config.read_text(encoding="utf-8"))
        best = Path(data.get("best_model_path", ""))
        if best.exists():
            return best

    candidates = sorted(
        (logs_dir / "checkpoints").glob(f"{model_name}-*.ckpt"),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError(f"Checkpoint {model_name} tidak ditemukan di {logs_dir / 'checkpoints'}")
    return candidates[-1]


def _smape(actual: np.ndarray, pred: np.ndarray) -> float:
    denominator = np.abs(actual) + np.abs(pred) + 1e-8
    return float(np.mean(2.0 * np.abs(pred - actual) / denominator) * 100.0)


def _pinball(actual: np.ndarray, quantiles: np.ndarray, taus: list[float]) -> float:
    losses = []
    for index, tau in enumerate(taus):
        error = actual - quantiles[:, index]
        losses.append(np.mean(np.maximum(tau * error, (tau - 1.0) * error)))
    return float(np.mean(losses))


def _metrics(actual: np.ndarray, p10: np.ndarray, p50: np.ndarray, p90: np.ndarray,
             taus: list[float], has_interval: bool = True) -> dict:
    error = p50 - actual
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "bias": float(np.mean(error)),
        "smape_pct": _smape(actual, p50),
        "picp_80": float(np.mean((actual >= p10) & (actual <= p90))) if has_interval else float("nan"),
        "mpiw": float(np.mean(p90 - p10)) if has_interval else float("nan"),
        "pinball": _pinball(actual, np.column_stack([p10, p50, p90]), taus) if has_interval else float("nan"),
        "n": int(actual.size),
    }


def _plot_timeseries(frame: pd.DataFrame, out_path: Path, title: str, has_interval: bool) -> None:
    aggregated = (
        frame.groupby("time_idx")
        .agg(actual=("actual", "first"), p10=("p10", "mean"),
             p50=("p50", "mean"), p90=("p90", "mean"))
        .sort_index()
    )
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(aggregated.index, aggregated["actual"], color="#1f2937", lw=1.2, label="Aktual")
    ax.plot(aggregated.index, aggregated["p50"], color="#b91c1c", lw=1.4, label="P50")
    if has_interval:
        ax.fill_between(aggregated.index, aggregated["p10"], aggregated["p90"],
                        color="#ef4444", alpha=0.18, label="P10-P90")
    ax.set_xlabel("time_idx (hari)")
    ax.set_ylabel(title)
    ax.set_title("Rata-rata prediksi lintas origin uji (bukan satu forecast)")
    ax.legend(loc="upper right", frameon=False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def _plot_last_window(frame: pd.DataFrame, date_map: pd.Series, out_path: Path,
                      title: str, has_interval: bool, horizon: int) -> None:
    last_start = int(frame["start_idx"].max())
    window = frame[frame["start_idx"] == last_start].sort_values("horizon")
    if window.empty:
        return
    x = [date_map.get(int(t)) for t in window["time_idx"]]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.plot(x, window["actual"], marker="o", color="#1f2937", label="Aktual")
    ax.plot(x, window["p50"], marker="o", color="#b91c1c", label="P50")
    if has_interval:
        ax.fill_between(x, window["p10"], window["p90"], color="#ef4444", alpha=0.2,
                        label="P10-P90")
    ax.set_ylabel(title)
    ax.set_title(f"Forecast {horizon} hari pada origin uji terakhir")
    ax.tick_params(axis="x", rotation=30)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def evaluate(cfg: dict, model_name: str, checkpoint: str | None = None) -> dict:
    data_path = resolve(cfg, cfg["data"]["processed_dir"]) / "bromo_daily.parquet"
    data = pd.read_parquet(data_path)
    target = cfg["data"]["target"]

    checkpoint_path = resolve_checkpoint(cfg, model_name, checkpoint)
    print(f"[eval] model={model_name} | checkpoint={checkpoint_path}")
    model = load_checkpoint(model_name, str(checkpoint_path), map_location="cpu")
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

    has_interval = getattr(model.loss, "quantiles", None) is not None
    if has_interval:
        prediction = model.predict(
            loader,
            mode="quantiles",
            return_x=True,
            return_index=True,
            trainer_kwargs={"logger": False},
        )
        values = prediction.output.detach().cpu().numpy()
        if values.ndim != 3:
            raise ValueError(f"Bentuk output tak terduga: {values.shape}")
        taus = [float(q) for q in model.loss.quantiles]
        if sorted(taus) != [0.1, 0.5, 0.9]:
            raise ValueError(
                f"Checkpoint memakai quantiles {taus}; evaluasi ini hanya mendukung [0.1, 0.5, 0.9]."
            )
        q10 = int(np.argmin(np.abs(np.array(taus) - 0.10)))
        q50 = int(np.argmin(np.abs(np.array(taus) - 0.50)))
        q90 = int(np.argmin(np.abs(np.array(taus) - 0.90)))
    else:
        prediction = model.predict(
            loader,
            mode="prediction",
            return_x=True,
            return_index=True,
            trainer_kwargs={"logger": False},
        )
        values = prediction.output.detach().cpu().numpy()
        if values.ndim == 3:
            values = values[..., 0]
        if values.ndim != 2:
            raise ValueError(f"Bentuk output tak terduga: {values.shape}")
        taus = []
        q10 = q50 = q90 = 0

    index = prediction.index.reset_index(drop=True)
    decoder_time = prediction.x["decoder_time_idx"].detach().cpu().numpy()
    if len(index) != values.shape[0] or decoder_time.shape != values.shape[:2]:
        raise ValueError(
            f"Prediction/index shape mismatch: values={values.shape}, "
            f"index={len(index)}, decoder_time={decoder_time.shape}"
        )
    actual_series = data.set_index("time_idx")[target]
    date_map = pd.Series(data.index, index=data["time_idx"].to_numpy())

    rows = []
    for row_idx in range(len(index)):
        for horizon in range(values.shape[1]):
            time_idx = int(decoder_time[row_idx, horizon])
            if time_idx not in actual_series.index:
                continue
            point_values = values[row_idx, horizon]
            if not np.isfinite(point_values).all():
                continue
            if has_interval:
                p10, p50, p90 = (
                    float(point_values[q10]),
                    float(point_values[q50]),
                    float(point_values[q90]),
                )
            else:
                p10 = p50 = p90 = float(point_values)
            rows.append(
                {
                    "window": row_idx,
                    "start_idx": int(decoder_time[row_idx, 0]),
                    "time_idx": time_idx,
                    "horizon": horizon + 1,
                    "actual": float(actual_series.loc[time_idx]),
                    "p10": p10,
                    "p50": p50,
                    "p90": p90,
                }
            )

    prediction_frame = pd.DataFrame(rows)
    if prediction_frame.empty:
        raise RuntimeError("Tidak ada prediksi valid. Cek split test / panjang encoder.")

    results_dir = resolve(cfg, cfg["paths"]["results"]) / model_name
    results_dir.mkdir(parents=True, exist_ok=True)
    prediction_frame.to_csv(results_dir / "predictions.csv", index=False)

    overall = _metrics(
        prediction_frame["actual"].to_numpy(),
        prediction_frame["p10"].to_numpy(),
        prediction_frame["p50"].to_numpy(),
        prediction_frame["p90"].to_numpy(),
        taus,
        has_interval=has_interval,
    )
    overall["n_origins"] = int(prediction_frame["window"].nunique())

    per_horizon = []
    for horizon, group in prediction_frame.groupby("horizon"):
        metrics = _metrics(
            group["actual"].to_numpy(),
            group["p10"].to_numpy(),
            group["p50"].to_numpy(),
            group["p90"].to_numpy(),
            taus,
            has_interval=has_interval,
        )
        metrics["horizon"] = int(horizon)
        per_horizon.append(metrics)
    per_horizon_frame = pd.DataFrame(per_horizon).sort_values("horizon")
    per_horizon_frame.to_csv(results_dir / "metrics_per_horizon.csv", index=False)

    summary = {
        "model": model_name,
        "checkpoint": str(checkpoint_path),
        "target": target,
        "quantiles": taus,
        "test_windows": int(prediction_frame["window"].nunique()),
        "overall": overall,
        "per_horizon": per_horizon,
        "scope_note": (
            "Metrics pool overlapping test windows. overall.n counts horizon observations, "
            "not independent days; overall.n_origins is the number of forecast origins."
        ),
    }
    (results_dir / "metrics.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    label = target_label(cfg)
    horizon = int(values.shape[1])
    _plot_timeseries(prediction_frame, results_dir / "actual_vs_pred.png", label, has_interval)
    _plot_last_window(prediction_frame, date_map, results_dir / "forecast_last_window.png",
                      label, has_interval, horizon)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(per_horizon_frame["horizon"], per_horizon_frame["rmse"], color="#b91c1c")
    ax.set_xlabel("Horizon (hari)")
    ax.set_ylabel("RMSE (C)")
    ax.set_title("RMSE per horizon")
    fig.tight_layout()
    fig.savefig(results_dir / "rmse_per_horizon.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.hist(prediction_frame["p50"] - prediction_frame["actual"], bins=40, color="#1f2937", alpha=0.8)
    ax.axvline(0, color="#b91c1c", lw=1)
    ax.set_xlabel("Residual P50 - aktual (C)")
    ax.set_ylabel("Frekuensi")
    ax.set_title("Distribusi residual")
    fig.tight_layout()
    fig.savefig(results_dir / "residuals.png", dpi=180)
    plt.close(fig)

    print(
        f"[ok] MAE={overall['mae']:.3f} RMSE={overall['rmse']:.3f} "
        f"SMAPE={overall['smape_pct']:.2f}% PICP80={overall['picp_80']:.3f} "
        f"origins={overall['n_origins']} n={overall['n']}"
    )
    print(f"[ok] artefak: {results_dir}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluasi model TFT/LSTM Bromo")
    parser.add_argument("--config", default=None)
    parser.add_argument("--model", choices=("tft", "lstm"), default="tft")
    parser.add_argument("--checkpoint", default=None)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    evaluate(cfg, args.model, checkpoint=args.checkpoint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
