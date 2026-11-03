"""Loader konfigurasi + utilitas tanggal untuk seluruh pipeline."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs/bromo.yaml"
TARGET_LABELS = {
    "t2m_min_c": "Suhu minimum",
    "t2m_mean_c": "Suhu rata-rata",
    "t2m_max_c": "Suhu maksimum",
}


def target_label(cfg: dict[str, Any]) -> str:
    target = str(cfg["data"]["target"])
    return TARGET_LABELS.get(target, target)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    with open(config_path, "r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    cfg["_root"] = ROOT
    return cfg


def resolve(cfg: dict[str, Any], value: str | Path) -> Path:
    """Path relatif selalu di-resolve dari root folder luaran_jurnal_sinta/."""
    path = Path(value)
    return path if path.is_absolute() else cfg["_root"] / path


def month_range(start_date: str | date, end_date: str | date) -> list[tuple[int, int]]:
    """Daftar (tahun, bulan) inklusif antara dua tanggal."""
    start = date.fromisoformat(str(start_date))
    end = date.fromisoformat(str(end_date))
    if start > end:
        raise ValueError(f"start_date {start} > end_date {end}")

    months: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        month += 1
        if month == 13:
            month = 1
            year += 1
    return months
