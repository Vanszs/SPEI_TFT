"""Regression checks untuk logika non-trivial pipeline (stdlib unittest, tanpa pytest)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import month_range  # noqa: E402
from src.evaluate import _metrics  # noqa: E402
from src.preprocess import _deaccumulate, aggregate_daily  # noqa: E402


class TestDeaccumulate(unittest.TestCase):
    def test_constant_rain_is_not_summed_as_accumulation(self):
        times = pd.date_range("2021-01-01", periods=48, freq="h")
        hour = times.hour.to_numpy()
        raw_mm = np.where(hour == 0, 24.0, hour.astype(float))
        increments = _deaccumulate(raw_mm, times)
        self.assertAlmostEqual(float(np.nansum(increments[24:48])), 24.0)
        self.assertAlmostEqual(float(np.nansum(increments[1:24])), 23.0)

    def test_negative_flux_is_preserved(self):
        times = pd.date_range("2021-01-01", periods=48, freq="h")
        hour = times.hour.to_numpy()
        raw_mj = np.where(hour == 0, -24.0, -hour.astype(float))
        increments = _deaccumulate(raw_mj * 1e6, times) / 1e6
        self.assertAlmostEqual(float(np.nansum(increments[24:48])), -24.0)


class TestAggregateDaily(unittest.TestCase):
    def _frame(self, days: int, hours_last_day: int = 24) -> pd.DataFrame:
        rows = []
        start = pd.Timestamp("2021-01-01")
        for day in range(days):
            n_hours = hours_last_day if day == days - 1 else 24
            for hour in range(n_hours):
                rows.append(
                    {
                        "date": start + pd.Timedelta(days=day),
                        "t2m_c": 10.0 + hour,
                        "d2m_c": 8.0,
                        "net_thermal_mj": -1.0,
                        "wind_speed": 1.0,
                        "tp_mm": 1.0,
                    }
                )
        return pd.DataFrame(rows)

    def test_partial_day_is_dropped(self):
        daily, stats = aggregate_daily(self._frame(3, hours_last_day=7), "t2m_min_c", 3)
        self.assertEqual(len(daily), 2)
        self.assertEqual(stats["partial_days_dropped"], 1)
        self.assertTrue((daily["tp_mm"] == 24.0).all())

    def test_missing_target_is_not_imputed(self):
        frame = self._frame(3)
        mask = frame["date"] == pd.Timestamp("2021-01-02")
        frame.loc[mask, "t2m_c"] = np.nan
        daily, stats = aggregate_daily(frame, "t2m_min_c", 3)
        self.assertNotIn(pd.Timestamp("2021-01-02"), daily.index)
        self.assertEqual(stats["target_missing_dropped"], 1)

    def test_partial_hourly_input_drops_the_day(self):
        frame = self._frame(3)
        mask = (frame["date"] == pd.Timestamp("2021-01-02")) & (frame["t2m_c"] == 10.0)
        frame.loc[mask, "t2m_c"] = np.nan
        daily, stats = aggregate_daily(frame, "t2m_min_c", 3)
        self.assertNotIn(pd.Timestamp("2021-01-02"), daily.index)
        self.assertEqual(stats["partial_days_dropped"], 1)


class TestConfigAndMetrics(unittest.TestCase):
    def test_month_range_is_inclusive(self):
        self.assertEqual(month_range("2021-01-15", "2021-03-02"), [(2021, 1), (2021, 2), (2021, 3)])

    def test_metrics_zero_error(self):
        metrics = _metrics(
            np.array([1.0, 2.0]),
            np.array([0.0, 0.0]),
            np.array([1.0, 2.0]),
            np.array([2.0, 3.0]),
            [0.1, 0.5, 0.9],
        )
        self.assertAlmostEqual(metrics["mae"], 0.0)
        self.assertAlmostEqual(metrics["rmse"], 0.0)
        self.assertAlmostEqual(metrics["picp_80"], 1.0)
        self.assertEqual(metrics["n"], 2)


if __name__ == "__main__":
    unittest.main()
