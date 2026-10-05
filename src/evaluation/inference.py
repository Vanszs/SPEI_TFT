"""Real TFT inference for the FastAPI layer (replaces the previous dummy endpoint).

Resolves the best checkpoint from logs/run_config.json (fallback: newest
logs/checkpoints/*.ckpt), rebuilds the TimeSeriesDataSet from the processed
parquet, appends genuine future rows for the known covariates, and produces
P10/P50/P90 forecasts for the unobserved horizon after the last observation.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from pytorch_forecasting import TimeSeriesDataSet

from src.evaluation.calibration import apply_calibration, fit_per_city_interval_calibration
from src.models.dataset import MODEL_GROUP_COL, create_dataset
from src.models.tft import load_tft_checkpoint

DEFAULT_DATA_PATH = "data/processed/spei_dataset.parquet"

# Covariates that are known into the future (thesis BAB III Tabel 3.6).
# month_sin/cos are recomputed for future dates; other unknown-series covariates
# cannot be known ahead and will be filled (see _append_future_rows).
KNOWN_REALS = ["time_idx", "month_sin", "month_cos"]


def _resolve_checkpoint(explicit: str | None = None) -> str:
    if explicit and Path(explicit).exists():
        return explicit

    cfg = Path("logs/run_config.json")
    if cfg.exists():
        try:
            best = json.loads(cfg.read_text(encoding="utf-8")).get("best_model_path")
            if best and Path(best).exists():
                return best
        except (json.JSONDecodeError, OSError):
            pass

    import re

    ckpts = sorted(Path("logs/checkpoints").glob("*.ckpt"))
    scored = []
    for p in ckpts:
        m = re.search(r"val_loss=(\d+\.\d+)", p.name)
        if m:
            scored.append((float(m.group(1)), str(p)))
    if scored:
        return min(scored)[1]
    if ckpts:
        return str(ckpts[-1])
    raise FileNotFoundError("No TFT checkpoint found in logs/checkpoints.")


def _quantile_index_map(model):
    quantiles = [float(q) for q in getattr(model.loss, "quantiles", [0.1, 0.5, 0.9])]
    arr = np.array(quantiles)
    return {"p10": int(np.argmin(np.abs(arr - 0.10))),
            "p50": int(np.argmin(np.abs(arr - 0.50))),
            "p90": int(np.argmin(np.abs(arr - 0.90)))}


class InferenceBundle:
    """Loaded model + dataset + city index. Build once at startup."""

    def __init__(self, data_path: str = DEFAULT_DATA_PATH, checkpoint_path: str | None = None):
        if not Path(data_path).exists():
            raise FileNotFoundError(f"Processed dataset not found: {data_path}")
        self.data_path = data_path
        self.checkpoint_path = _resolve_checkpoint(checkpoint_path)
        self.data = pd.read_parquet(data_path)
        self.data["time"] = pd.to_datetime(self.data["time"])
        # Map a decoder time_idx back to a calendar date. time_idx counts days
        # from the min *post-dropna* date, so the anchor is that date, not min(time).
        first = self.data.sort_values("time_idx").iloc[0]
        self.time_idx_anchor = pd.Timestamp(first["time"]) - pd.Timedelta(days=int(first["time_idx"]))
        self.last_observed_time = self.data["time"].max()
        self.model = load_tft_checkpoint(self.checkpoint_path, map_location="cpu")
        self.model.eval()
        self.model.to("cpu")
        self.qidx = _quantile_index_map(self.model)
        self.pred_len = int(getattr(self.model.hparams, "max_prediction_length", 30))
        self.train_ds = create_dataset(self.data)
        self.cities = {
            str(c): str(e)
            for c, e in self.data.groupby("city_id")[MODEL_GROUP_COL].first().items()
        }
        self.entity_ids = set(self.data[MODEL_GROUP_COL].astype(str))
        for e in self.entity_ids:
            self.cities.setdefault(e, e)
        self.calibration_factors = self._fit_calibration()

    def _fit_calibration(self) -> dict:
        """Faktor kalibrasi per kota dari data validasi 2023 (jalur yang sama dengan
        full_evaluation.apply_calibration). Tanpa ini interval web lebih sempit dari
        yang dilaporkan PICP."""
        val = self.data[pd.to_datetime(self.data["time"]).dt.year == 2023]
        if val.empty:
            return {}
        rows = []
        for city in sorted(val["city_id"].astype(str).unique()):
            ent = self._entity_for(city)
            loc = self.data[self.data[MODEL_GROUP_COL].astype(str) == ent].sort_values("time")
            if len(loc) < self.pred_len + 10:
                continue
            loc_ds = TimeSeriesDataSet.from_dataset(
                self.train_ds, loc, predict=False, stop_randomization=True
            )
            loader = loc_ds.to_dataloader(train=False, batch_size=64, num_workers=0)
            raw = self.model.predict(
                loader, mode="raw", return_x=True,
                trainer_kwargs={"accelerator": "cpu", "devices": 1},
            )
            preds = raw.output.prediction.cpu().numpy()
            t_idx = raw.x["decoder_time_idx"].cpu().numpy()
            step0 = {}
            for i in range(preds.shape[0]):
                key = int(t_idx[i, 0])
                if key not in step0:
                    step0[key] = (
                        float(preds[i, 0, self.qidx["p10"]]),
                        float(preds[i, 0, self.qidx["p50"]]),
                        float(preds[i, 0, self.qidx["p90"]]),
                    )
            for key, (p10, p50, p90) in step0.items():
                rows.append({"city_id": city, "time_idx": key,
                             "pred_p10": p10, "pred_p50": p50, "pred_p90": p90})
        if not rows:
            return {}
        frame = pd.DataFrame(rows)
        actual = val[["city_id", "time_idx", "SPEI_3"]].rename(columns={"SPEI_3": "actual"})
        merged = pd.merge(actual, frame, on=["city_id", "time_idx"], how="inner")
        if len(merged) <= 10:
            return {}
        return fit_per_city_interval_calibration(merged, city_col="city_id")

    def _entity_for(self, city_id: str) -> str:
        if city_id in self.cities:
            return self.cities[city_id]
        if city_id in self.entity_ids:
            return city_id
        raise KeyError(f"Unknown city/entity: {city_id}")

    def _append_future_rows(self, loc: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Append `horizon` future rows for the entity, populating known covariates.

        Future dates are unobserved, so unknown time-varying covariates are set
        NaN and the model relies on its QuantileLoss/decoder path. Known
        covariates (time_idx, month_sin, month_cos) are exact.
        """
        last = loc.iloc[-1]
        future_idx = np.arange(int(last["time_idx"]) + 1, int(last["time_idx"]) + 1 + horizon)
        future_time = [
            (self.time_idx_anchor + pd.Timedelta(days=int(t))) for t in future_idx
        ]
        future = pd.DataFrame(index=range(horizon))
        for col in self.data.columns:
            future[col] = last[col]
        future[MODEL_GROUP_COL] = str(last[MODEL_GROUP_COL])
        future["time"] = future_time
        future["time_idx"] = future_idx
        months = pd.DatetimeIndex(future_time).month
        future["month_sin"] = np.sin(2 * np.pi * months / 12)
        future["month_cos"] = np.cos(2 * np.pi * months / 12)
        # Future unknown-ahead covariates (target + hydroclimatic series) are not
        # observed. They are carried forward from the last observation purely to
        # satisfy the dataset validator; the decoder target is not used to produce
        # the forecast (predictions come from the known decoder covariates +
        # attention). Documented limitation, not fabricated observations.
        for col in (
            "SPEI_3",
            "SPEI_3_diff",
            "water_deficit",
            "precipitation_log",
            "et0_fao_evapotranspiration",
            "soil_moisture",
            "temperature_2m_max",
            "temperature_2m_min",
            "relative_humidity_2m_mean",
            "shortwave_radiation_sum",
            "wind_speed_10m_mean",
        ):
            if col in future.columns:
                future[col] = last[col]
        return pd.concat([loc, future], ignore_index=True)

    def forecast(self, city_id: str, forecast_days: int = 30) -> dict:
        """Forecast the next `forecast_days` unobserved steps for a city.

        Appends genuine future rows so the returned dates fall strictly after the
        last observation, then reads the model's quantile outputs for that horizon.
        """
        entity = self._entity_for(city_id)
        loc = self.data[self.data[MODEL_GROUP_COL].astype(str) == entity].sort_values("time")
        horizon = min(int(forecast_days), self.pred_len)
        future_loc = self._append_future_rows(loc, horizon)
        pred_ds = TimeSeriesDataSet.from_dataset(
            self.train_ds, future_loc, predict=True, stop_randomization=True
        )
        loader = pred_ds.to_dataloader(train=False, batch_size=1, num_workers=0)
        raw = self.model.predict(
            loader,
            mode="raw",
            return_x=True,
            trainer_kwargs={"accelerator": "cpu", "devices": 1},
        )
        preds = raw.output.prediction.cpu().numpy()[0]          # [horizon, n_quantiles]
        time_idx = raw.x["decoder_time_idx"].cpu().numpy()[0]   # [horizon]

        # Kalibrasi per kota: samakan lebar interval dengan yang dilaporkan PICP.
        factor = float(self.calibration_factors.get(city_id, self.calibration_factors.get(entity, 1.0)))
        if factor != 1.0:
            p10 = preds[:, self.qidx["p10"]]
            p90 = preds[:, self.qidx["p90"]]
            p50 = preds[:, self.qidx["p50"]]
            half = (p90 - p10) / 2.0
            preds = preds.copy()
            preds[:, self.qidx["p10"]] = p50 - half * factor
            preds[:, self.qidx["p90"]] = p50 + half * factor

        n = min(horizon, preds.shape[0])
        dates = [
            (self.time_idx_anchor + pd.Timedelta(days=int(t))).date().isoformat()
            for t in time_idx[-n:]
        ]
        return {
            "city_id": city_id,
            "dates": dates,
            "p10": [float(preds[-(n - i), self.qidx["p10"]]) for i in range(n)],
            "p50": [float(preds[-(n - i), self.qidx["p50"]]) for i in range(n)],
            "p90": [float(preds[-(n - i), self.qidx["p90"]]) for i in range(n)],
        }


def build_bundle(data_path: str = DEFAULT_DATA_PATH, checkpoint_path: str | None = None):
    return InferenceBundle(data_path=data_path, checkpoint_path=checkpoint_path)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Real TFT inference smoke test")
    ap.add_argument("--city", default="Bojonegoro")
    ap.add_argument("--days", type=int, default=5)
    args = ap.parse_args()
    torch.set_float32_matmul_precision("medium")
    b = build_bundle()
    out = b.forecast(args.city, args.days)
    print("checkpoint:", b.checkpoint_path)
    print("entity    :", b._entity_for(args.city))
    print("dates     :", out["dates"])
    print("p50       :", [round(v, 4) for v in out["p50"]])
