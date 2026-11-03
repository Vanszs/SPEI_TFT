"""Konstruksi TimeSeriesDataSet TFT untuk satu seri titik Bromo."""

from __future__ import annotations

from typing import Any

import pandas as pd
from pytorch_forecasting import TimeSeriesDataSet
from pytorch_forecasting.data.encoders import EncoderNormalizer
from sklearn.preprocessing import StandardScaler

GROUP_COL = "series_id"
KNOWN_REALS = ["month_sin", "month_cos", "doy_sin", "doy_cos", "is_dry_season"]
UNKNOWN_REALS = ["d2m_c", "dewpoint_depression", "net_thermal_mj", "wind_speed", "tp_mm"]


def _validate_frame(data: pd.DataFrame, target: str) -> None:
    required = {"time_idx", "split", GROUP_COL, target, *KNOWN_REALS, *UNKNOWN_REALS}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Kolom dataset hilang: {sorted(missing)}. Jalankan preprocess dulu.")
    if data[GROUP_COL].nunique() != 1:
        raise ValueError(f"Pipeline ini untuk satu titik; ditemukan {data[GROUP_COL].nunique()} seri.")


def build_training_dataset(
    data: pd.DataFrame,
    cfg: dict[str, Any],
    include_past_covariates: bool = True,
) -> TimeSeriesDataSet:
    """Bangun dataset training.

    include_past_covariates=False dipakai baseline LSTM: RecurrentNetwork hanya
    menerima kovariat yang diketahui sampai horizon prediksi, sehingga kovariat
    masa lalu (d2m, radiasi, angin, hujan) tidak boleh masuk sebagai unknown.
    Baseline menjadi LSTM univariat + fitur kalender.
    """
    model_cfg = cfg["model"]
    data_cfg = cfg["data"]
    target = data_cfg["target"]
    _validate_frame(data, target)

    train_df = data[data["split"] == "train"].copy()
    encoder_length = int(model_cfg["max_encoder_length"])
    prediction_length = int(model_cfg["max_prediction_length"])
    if len(train_df) < encoder_length + prediction_length:
        raise ValueError(
            f"Data train hanya {len(train_df)} baris; butuh minimal "
            f"{encoder_length + prediction_length}."
        )

    for column in (GROUP_COL, "split"):
        train_df[column] = train_df[column].astype(str)

    unknown_reals = [target, *UNKNOWN_REALS] if include_past_covariates else [target]
    scalers = {name: StandardScaler() for name in UNKNOWN_REALS} if include_past_covariates else {}

    return TimeSeriesDataSet(
        train_df,
        time_idx="time_idx",
        target=target,
        group_ids=[GROUP_COL],
        min_encoder_length=encoder_length,
        max_encoder_length=encoder_length,
        min_prediction_length=prediction_length,
        max_prediction_length=prediction_length,
        static_categoricals=[GROUP_COL],
        time_varying_known_reals=KNOWN_REALS,
        time_varying_unknown_reals=unknown_reals,
        target_normalizer=EncoderNormalizer(transformation=None),
        scalers=scalers,
        add_relative_time_idx=True,
        add_target_scales=True,
        allow_missing_timesteps=True,
    )


def split_frame(data: pd.DataFrame, split: str, encoder_length: int) -> pd.DataFrame:
    part = data[data["split"] == split]
    if part.empty:
        raise ValueError(f"Split '{split}' kosong.")
    start = int(part["time_idx"].min()) - encoder_length
    end = int(part["time_idx"].max())
    return data[(data["time_idx"] >= start) & (data["time_idx"] <= end)].copy()


def build_eval_dataset(
    training_dataset: TimeSeriesDataSet,
    data: pd.DataFrame,
    split: str,
    cfg: dict[str, Any],
) -> TimeSeriesDataSet:
    frame = split_frame(data, split, int(cfg["model"]["max_encoder_length"]))
    for column in (GROUP_COL, "split"):
        frame[column] = frame[column].astype(str)
    return TimeSeriesDataSet.from_dataset(
        training_dataset,
        frame,
        predict=False,
        stop_randomization=True,
    )


def dataloader(dataset: TimeSeriesDataSet, cfg: dict[str, Any], train: bool = False):
    model_cfg = cfg["model"]
    return dataset.to_dataloader(
        train=train,
        batch_size=int(model_cfg["batch_size"]),
        num_workers=int(model_cfg.get("num_workers", 0)),
        pin_memory=False,
    )
