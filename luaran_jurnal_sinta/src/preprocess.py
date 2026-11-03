"""Bersihkan ERA5-Land mentah menjadi tabel harian siap-TFT.

Input : data/raw/era5_land_bromo_<YYYYMM>.nc (hourly, accumulated tp/str)
Output: data/processed/bromo_daily.parquet + .meta.json

Dua hal yang mudah salah pada ERA5-Land:
1. `tp` dan `str` adalah akumulasi sejak 00 UTC, bukan nilai per jam. Nilai
   per jam = selisih terhadap jam sebelumnya, dengan reset pada 01 UTC.
2. Agregasi harian memakai waktu lokal Asia/Jakarta (UTC+7), bukan UTC, supaya
   suhu minimum harian benar-benar berasal dari malam lokal Bromo.

Hari yang tidak memiliki 24 sampel valid dibuang, bukan diisi. Target tidak
diinterpolasi: nilai target yang hilang berarti hari itu dibuang.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from src.config import load_config, month_range, resolve

CANONICAL_VARIABLES = {
    "t2m": ("t2m", "2m_temperature"),
    "d2m": ("d2m", "2m_dewpoint_temperature"),
    "str": ("str", "surface_net_thermal_radiation"),
    "u10": ("u10", "10m_u_component_of_wind"),
    "v10": ("v10", "10m_v_component_of_wind"),
    "tp": ("tp", "total_precipitation"),
}

NUMERIC_COLUMNS = [
    "t2m_min_c",
    "t2m_mean_c",
    "t2m_max_c",
    "d2m_c",
    "dewpoint_depression",
    "net_thermal_mj",
    "wind_speed",
    "tp_mm",
]

HOURLY_COLUMNS = ["t2m_c", "d2m_c", "net_thermal_mj", "wind_speed", "tp_mm"]

TARGET_DEFINITIONS = {
    "t2m_min_c": "minimum of 24 hourly 2m temperature samples in the local day",
    "t2m_mean_c": "mean of 24 hourly 2m temperature samples in the local day",
    "t2m_max_c": "maximum of 24 hourly 2m temperature samples in the local day",
}


def _rename_coords(ds: xr.Dataset) -> xr.Dataset:
    # File baru CDS menyimpan 'time' sebagai scalar referensi + 'valid_time' sebagai dimensi.
    # Drop scalar 'time' lebih dulu supaya rename valid_time -> time tidak bentrok.
    has_valid_time = "valid_time" in ds.dims or (
        "valid_time" in ds.coords and "time" not in ds.dims
    )
    if has_valid_time and "time" in ds.coords and "time" not in ds.dims:
        ds = ds.drop_vars("time")

    rename_map = {}
    if has_valid_time:
        rename_map["valid_time"] = "time"
    if "lat" in ds.dims or "lat" in ds.coords:
        rename_map["lat"] = "latitude"
    if "lon" in ds.dims or "lon" in ds.coords:
        rename_map["lon"] = "longitude"
    if rename_map:
        ds = ds.rename(rename_map)
    return ds


def _rename_variables(ds: xr.Dataset) -> xr.Dataset:
    for short_name, aliases in CANONICAL_VARIABLES.items():
        found = next((name for name in aliases if name in ds.data_vars), None)
        if found is None:
            raise KeyError(
                f"Variabel {short_name} tidak ditemukan. Tersedia: {sorted(ds.data_vars)}"
            )
        if found != short_name:
            ds = ds.rename({found: short_name})
    return ds


def load_raw(raw_dir: Path, expected_months: list[tuple[int, int]]) -> xr.Dataset:
    pattern = "era5_land_bromo_??????.nc"
    paths = sorted(raw_dir.glob(pattern))
    if not paths:
        raise FileNotFoundError(
            f"Tidak ada file {pattern} di {raw_dir}. Jalankan: python -m src.acquire_era5"
        )

    expected_names = {
        f"era5_land_bromo_{year}{month:02d}.nc" for year, month in expected_months
    }
    found_names = {path.name for path in paths}
    missing = sorted(expected_names - found_names)
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} file bulanan hilang, contoh: {missing[:3]}. "
            "Jalankan ulang acquire_era5 sebelum preprocess."
        )

    parts = []
    for path in paths:
        with xr.open_dataset(path) as opened:
            parts.append(_rename_coords(opened).load())

    ds = xr.concat(parts, dim="time", coords="minimal", combine_attrs="override")
    ds = _rename_variables(ds)
    if "time" not in ds.indexes:
        raise ValueError("Dataset ERA5-Land tidak memiliki koordinat waktu.")
    if not ds.indexes["time"].is_unique:
        raise ValueError("Koordinat waktu duplikat; cek file mentah.")
    if ds.sizes.get("time", 0) == 0:
        raise ValueError("Dataset ERA5-Land kosong.")
    ds = ds.sortby("time")

    for name in CANONICAL_VARIABLES:
        if bool(ds[name].isnull().all()):
            raise ValueError(f"Variabel {name} seluruhnya NaN; file mentah rusak.")
    return ds


def select_point(ds: xr.Dataset, lat: float, lon: float) -> xr.Dataset:
    lon_values = np.asarray(ds["longitude"].values, dtype=float)
    if np.nanmax(lon_values) > 180.0 and lon < 0:
        lon = lon % 360.0
    return ds.sel(latitude=lat, longitude=lon, method="nearest").squeeze(drop=True)


def _deaccumulate(values: np.ndarray, times: pd.DatetimeIndex) -> np.ndarray:
    """Ubah akumulasi 00-UTC menjadi increment per jam.

    ECMWF: nilai pada 01 UTC adalah akumulasi 1 jam pertama hari itu; nilai pada
    02..23 UTC adalah akumulasi sejak 00 UTC; nilai pada 00 UTC berikutnya adalah
    total 24 jam. Karena itu diff biasa benar untuk 00 UTC, sedangkan 01 UTC
    harus diambil langsung dari nilai mentah (reset harian).
    """
    series = pd.Series(np.asarray(values, dtype=float).reshape(-1), index=times)
    increments = series.diff()
    first_hour = series.index.hour == 1
    increments[first_hour] = series[first_hour]
    increments.iloc[0] = np.nan
    return increments.to_numpy()


def to_hourly_frame(point: xr.Dataset, timezone: str) -> pd.DataFrame:
    times = pd.to_datetime(point["time"].values)
    if not isinstance(times, pd.DatetimeIndex):
        times = pd.DatetimeIndex(times)
    if times.tz is None:
        times_local = times.tz_localize("UTC").tz_convert(timezone)
    else:
        times_local = times.tz_convert(timezone)

    t2m = np.asarray(point["t2m"].values, dtype=float).reshape(-1) - 273.15
    d2m = np.asarray(point["d2m"].values, dtype=float).reshape(-1) - 273.15
    tp_mm = np.clip(_deaccumulate(point["tp"].values * 1000.0, times), 0.0, None)
    net_thermal_mj = _deaccumulate(np.asarray(point["str"].values, dtype=float) / 1e6, times)

    frame = pd.DataFrame(
        {
            "t2m_c": t2m,
            "d2m_c": d2m,
            "net_thermal_mj": net_thermal_mj,
            "wind_speed": np.hypot(
                np.asarray(point["u10"].values, dtype=float).reshape(-1),
                np.asarray(point["v10"].values, dtype=float).reshape(-1),
            ),
            "tp_mm": tp_mm,
        }
    )
    frame["date"] = times_local.tz_localize(None).normalize().to_numpy()
    return frame.dropna(subset=["tp_mm", "net_thermal_mj"])


def aggregate_daily(
    frame: pd.DataFrame,
    target: str,
    max_gap_fill_days: int,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict]:
    frame = frame.dropna(subset=HOURLY_COLUMNS)
    counts = frame.groupby("date")["tp_mm"].count()
    complete_dates = counts[counts == 24].index
    partial_days_dropped = int((counts != 24).sum())
    frame = frame[frame["date"].isin(complete_dates)]
    if frame.empty:
        raise ValueError("Tidak ada hari lengkap 24 jam; cek rentang unduhan ERA5-Land.")

    daily = frame.groupby("date", sort=True).agg(
        t2m_min_c=("t2m_c", "min"),
        t2m_mean_c=("t2m_c", "mean"),
        t2m_max_c=("t2m_c", "max"),
        d2m_c=("d2m_c", "mean"),
        net_thermal_mj=("net_thermal_mj", "sum"),
        wind_speed=("wind_speed", "mean"),
        tp_mm=("tp_mm", "sum"),
    )
    daily["dewpoint_depression"] = daily["t2m_mean_c"] - daily["d2m_c"]

    full_index = pd.date_range(daily.index.min(), daily.index.max(), freq="D", name="date")
    daily = daily.reindex(full_index)
    if start is not None:
        daily = daily[daily.index >= start]
    if end is not None:
        daily = daily[daily.index <= end]
    if daily.empty:
        raise ValueError("Tidak ada hari di dalam rentang study.start_date/end_date.")

    target_missing = int(daily[target].isna().sum())
    imputed = {
        column: int(daily[column].isna().sum())
        for column in NUMERIC_COLUMNS
        if column != target
    }

    for column in NUMERIC_COLUMNS:
        if column == target:
            continue
        daily[column] = daily[column].interpolate(
            limit=max_gap_fill_days, limit_direction="both"
        )
    daily["tp_mm"] = daily["tp_mm"].fillna(0.0)

    # Target tidak diinterpolasi: metrik tidak boleh dinilai terhadap nilai sintetis.
    daily = daily.dropna(subset=[target])
    feature_gap_dropped = int(daily[NUMERIC_COLUMNS].isna().any(axis=1).sum())
    daily = daily.dropna(subset=NUMERIC_COLUMNS)

    stats = {
        "partial_days_dropped": partial_days_dropped,
        "target_missing_dropped": target_missing,
        "feature_gap_dropped": feature_gap_dropped,
        "imputed_values": imputed,
    }
    return daily, stats


def add_calendar_features(daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    month = daily.index.month.to_numpy()
    doy = daily.index.dayofyear.to_numpy()
    daily["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    daily["month_cos"] = np.cos(2 * np.pi * month / 12.0)
    daily["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    daily["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    daily["is_dry_season"] = np.isin(month, [6, 7, 8, 9]).astype(int)
    return daily


def add_split(daily: pd.DataFrame, ratios: dict) -> pd.DataFrame:
    total = sum(float(value) for value in ratios.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Rasio split harus berjumlah 1.0, ditemukan {total}.")

    daily = daily.copy()
    n = len(daily)
    n_train = int(n * float(ratios["train"]))
    n_val = int(n * float(ratios["val"]))
    if min(n_train, n_val, n - n_train - n_val) <= 0:
        raise ValueError(f"Data terlalu pendek untuk split yang diminta: {n} hari.")

    labels = np.array(["train"] * n_train + ["val"] * n_val + ["test"] * (n - n_train - n_val))
    daily["split"] = labels
    daily["series_id"] = "BROMO"
    daily["time_idx"] = (daily.index - daily.index.min()).days.astype(int)
    return daily


def preprocess(cfg: dict, raw_dir: Path | None = None, output_dir: Path | None = None) -> Path:
    study = cfg["study"]
    data_cfg = cfg["data"]
    target = data_cfg["target"]
    if target not in NUMERIC_COLUMNS:
        raise ValueError(f"Target tidak dikenal: {target}. Pilihan: {NUMERIC_COLUMNS}")
    raw_dir = raw_dir or resolve(cfg, data_cfg["raw_dir"])
    output_dir = output_dir or resolve(cfg, data_cfg["processed_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    expected_months = month_range(study["start_date"], study["end_date"])
    ds = load_raw(raw_dir, expected_months)
    point = select_point(ds, float(study["latitude"]), float(study["longitude"]))
    frame = to_hourly_frame(point, study["timezone"])
    start = pd.Timestamp(study["start_date"])
    end = pd.Timestamp(study["end_date"])
    daily, stats = aggregate_daily(
        frame,
        target,
        int(data_cfg["max_gap_fill_days"]),
        start=start,
        end=end,
    )

    daily = add_calendar_features(daily)
    daily = add_split(daily, data_cfg["split"])

    if target not in daily.columns:
        raise KeyError(f"Target {target} tidak ada. Pilihan: {NUMERIC_COLUMNS}")

    output = output_dir / "bromo_daily.parquet"
    daily.to_parquet(output)

    split_ranges = {
        name: {
            "start": str(daily[daily.split == name].index.min().date()),
            "end": str(daily[daily.split == name].index.max().date()),
            "rows": int((daily.split == name).sum()),
        }
        for name in ("train", "val", "test")
    }
    meta = {
        "study": study["name"],
        "requested_lat": float(study["latitude"]),
        "requested_lon": float(study["longitude"]),
        "grid_lat": float(point["latitude"].item()),
        "grid_lon": float(point["longitude"].item()),
        "timezone": study["timezone"],
        "target": target,
        "target_definition": TARGET_DEFINITIONS.get(target, target),
        "rows": int(len(daily)),
        "date_start": str(daily.index.min().date()),
        "date_end": str(daily.index.max().date()),
        "split": split_ranges,
        "target_stats": {
            "min": float(daily[target].min()),
            "mean": float(daily[target].mean()),
            "max": float(daily[target].max()),
        },
        "raw_files": len(expected_months),
        "raw_months_expected": len(expected_months),
        "hourly_rows": int(len(frame)),
        "accumulation_handling": "tp/str de-accumulated hourly increments (00 UTC reset)",
        "elevation_correction": "none; ERA5-Land grid-cell mean, not station elevation",
        "dropped": stats,
        "source": str(raw_dir),
    }
    meta_path = output.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[ok] {output} | {len(daily)} hari | target={target}")
    for name, info in split_ranges.items():
        print(f"     {name:5s}: {info['start']} .. {info['end']} ({info['rows']} hari)")
    print(
        "     dropped: partial={partial_days_dropped} target_missing={target_missing_dropped} "
        "feature_gap={feature_gap_dropped}".format(**stats)
    )
    print(f"[ok] {meta_path}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preprocess ERA5-Land Bromo -> tabel harian")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    preprocess(load_config(args.config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
