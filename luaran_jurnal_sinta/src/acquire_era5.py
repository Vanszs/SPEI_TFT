"""Unduh ERA5-Land hourly untuk satu titik (Bromo) dari Copernicus CDS.

Output: data/raw/era5_land_bromo_<YYYYMM>.nc (satu file per bulan; request
bulanan menghindari tanggal tidak valid seperti 30 Februari). File diunduh ke
*.part lalu divalidasi sebelum di-rename, sehingga unduhan terputus tidak
pernah dianggap lengkap.

Prasyarat kredensial CDS:
    ~/.cdsapirc
    url: https://cds.climate.copernicus.eu/api
    key: <personal-access-token>

Contoh:
    python -m src.acquire_era5 --config configs/bromo.yaml
    python -m src.acquire_era5 --years 2016 2017 --overwrite
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
from pathlib import Path

import pandas as pd
import xarray as xr

from src.config import load_config, month_range, resolve

DATASET = "reanalysis-era5-land"
VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "surface_net_thermal_radiation",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "total_precipitation",
]
SHORT_VARIABLES = {
    "t2m": ("t2m", "2m_temperature"),
    "d2m": ("d2m", "2m_dewpoint_temperature"),
    "str": ("str", "surface_net_thermal_radiation"),
    "u10": ("u10", "10m_u_component_of_wind"),
    "v10": ("v10", "10m_v_component_of_wind"),
    "tp": ("tp", "total_precipitation"),
}
ALL_HOURS = [f"{h:02d}:00" for h in range(24)]
AREA_PADDING_DEG = 0.05


def build_request(cfg: dict, year: int, month: int) -> dict:
    study = cfg["study"]
    lat = float(study["latitude"])
    lon = float(study["longitude"])
    # CDS memakai urutan [North, West, South, East].
    area = [lat + AREA_PADDING_DEG, lon - AREA_PADDING_DEG, lat - AREA_PADDING_DEG, lon + AREA_PADDING_DEG]
    days_in_month = calendar.monthrange(year, month)[1]
    return {
        "product_type": ["reanalysis"],
        "variable": VARIABLES,
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": [f"{day:02d}" for day in range(1, days_in_month + 1)],
        "time": ALL_HOURS,
        "area": area,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def target_path(cfg: dict, year: int, month: int) -> Path:
    raw_dir = resolve(cfg, cfg["data"]["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir / f"era5_land_bromo_{year}{month:02d}.nc"


def validate_file(path: Path, year: int, month: int) -> tuple[bool, str]:
    try:
        with xr.open_dataset(path) as ds:
            if "valid_time" in ds.dims or (
                "valid_time" in ds.coords and "time" not in ds.dims
            ):
                time_name = "valid_time"
            else:
                time_name = "time"
            if time_name not in ds.coords and time_name not in ds.dims:
                return False, "tidak ada koordinat waktu"
            times = pd.to_datetime(ds[time_name].values)
            expected = 24 * calendar.monthrange(year, month)[1]
            if len(times) != expected:
                return False, f"jumlah jam {len(times)} != {expected}"
            if not pd.Index(times).is_unique:
                return False, "timestamp duplikat"

            names = set(ds.data_vars)
            for short_name, aliases in SHORT_VARIABLES.items():
                found = next((name for name in aliases if name in names), None)
                if found is None:
                    return False, f"variabel {short_name} hilang"
                if bool(ds[found].isnull().all()):
                    return False, f"variabel {short_name} seluruhnya NaN"
        return True, "ok"
    except Exception as exc:
        return False, f"tidak bisa dibaca: {exc}"


def acquire_month(cfg: dict, year: int, month: int, overwrite: bool = False) -> Path:
    path = target_path(cfg, year, month)
    part = path.with_name(path.stem + ".part.nc")

    if path.exists() and not overwrite:
        ok, reason = validate_file(path, year, month)
        if ok:
            print(f"[skip] {path.name} valid")
            return path
        print(f"[redownload] {path.name} tidak valid ({reason})")

    import cdsapi

    part.unlink(missing_ok=True)
    request = build_request(cfg, year, month)
    print(f"[cds] request {year}-{month:02d}: {len(VARIABLES)} variabel")
    try:
        cdsapi.Client().retrieve(DATASET, request, str(part))
    except Exception as exc:
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"Unduhan CDS gagal untuk {year}-{month:02d}: {exc}. "
            "Pastikan ~/.cdsapirc valid dan cdsapi>=0.7."
        ) from exc

    ok, reason = validate_file(part, year, month)
    if not ok:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"File {year}-{month:02d} tidak valid setelah unduh: {reason}")

    os.replace(part, path)
    print(f"[ok] {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unduh ERA5-Land hourly titik Bromo")
    parser.add_argument("--config", default=None)
    parser.add_argument("--years", nargs="*", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Cetak request tanpa memanggil CDS")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.years:
        months = [(year, month) for year in args.years for month in range(1, 13)]
    else:
        months = month_range(cfg["study"]["start_date"], cfg["study"]["end_date"])

    if args.dry_run:
        print(json.dumps(build_request(cfg, *months[0]), indent=2, ensure_ascii=False))
        return 0

    if not (Path.home() / ".cdsapirc").exists():
        print(
            "[error] ~/.cdsapirc tidak ditemukan. Buat file berisi:\n"
            "  url: https://cds.climate.copernicus.eu/api\n"
            "  key: <personal-access-token>"
        )
        return 1

    try:
        for year, month in months:
            acquire_month(cfg, year, month, overwrite=args.overwrite)
    except RuntimeError as exc:
        print(f"[error] {exc}")
        return 1

    available = [target_path(cfg, year, month) for year, month in months]
    missing = [path.name for path in available if not path.exists()]
    if missing:
        raise RuntimeError(f"{len(missing)} file belum tersedia, contoh: {missing[:3]}")
    print(f"[done] {len(available)} file bulanan valid di {resolve(cfg, cfg['data']['raw_dir'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
