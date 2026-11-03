"""Kontrak file mentah ERA5-Land tanpa memanggil jaringan CDS."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from src.acquire_era5 import build_request, validate_file


def _write_month(path: Path, year: int = 2021, month: int = 1, drop: str | None = None) -> None:
    days = pd.Period(f"{year}-{month:02d}", freq="M").days_in_month
    times = pd.date_range(f"{year}-{month:02d}-01", periods=24 * days, freq="h")
    shape = (len(times), 1, 1)
    data = {
        "t2m": (("valid_time", "latitude", "longitude"), np.full(shape, 280.0, dtype="float32")),
        "d2m": (("valid_time", "latitude", "longitude"), np.full(shape, 276.0, dtype="float32")),
        "str": (("valid_time", "latitude", "longitude"), np.full(shape, -1e6, dtype="float32")),
        "u10": (("valid_time", "latitude", "longitude"), np.ones(shape, dtype="float32")),
        "v10": (("valid_time", "latitude", "longitude"), np.ones(shape, dtype="float32")),
        "tp": (("valid_time", "latitude", "longitude"), np.full(shape, 0.001, dtype="float32")),
    }
    if drop:
        data.pop(drop)
    ds = xr.Dataset(
        data,
        coords={"valid_time": times, "latitude": [-7.9], "longitude": [112.9]},
    )
    ds.to_netcdf(path)


class TestAcquireContract(unittest.TestCase):
    def test_request_covers_every_day_of_month(self):
        request = build_request({"study": {"latitude": -7.9, "longitude": 112.9}}, 2024, 2)
        self.assertEqual(len(request["day"]), 29)

    def test_valid_month_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "era5_land_bromo_202101.nc"
            _write_month(path)
            ok, reason = validate_file(path, 2021, 1)
            self.assertTrue(ok, reason)

    def test_missing_variable_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "era5_land_bromo_202101.nc"
            _write_month(path, drop="tp")
            ok, reason = validate_file(path, 2021, 1)
            self.assertFalse(ok)
            self.assertIn("tp", reason)

    def test_truncated_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "era5_land_bromo_202101.nc"
            path.write_bytes(b"not a netcdf")
            ok, _ = validate_file(path, 2021, 1)
            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
