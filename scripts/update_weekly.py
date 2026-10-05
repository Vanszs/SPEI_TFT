"""Pembaruan data mingguan untuk inference (bukan retraining).

Model TFT dibekukan pada checkpoint terbaik; prakiraan 30 hari selalu dimulai
setelah observasi terakhir. Jadi yang perlu disegarkan tiap minggu adalah DATA,
bukan bobot model:

    fetch delta (end_date = kemarin)
        -> preprocess (SPEI + super-node + artefak seleksi)
        -> inference.forecast(30) per kota (checkpoint yang sama)
        -> frontend/public/forecast_30d.json

Rentang diambil hanya sejak `--since` (atau sejak tanggal baris terakhir di raw),
sehingga bukan 21 tahun data yang diunduh ulang.

Pakai:
    python -m scripts.update_weekly
    python -m scripts.update_weekly --since 2026-01-02 --dry-run
"""
import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/weather_history_east_java.parquet"
PROCESSED = ROOT / "data/processed/spei_dataset.parquet"
ARTIFACT = ROOT / "frontend/public/forecast_30d.json"
PY = sys.executable

OBS_DAYS = 30
FU_DAYS = 30
CITIES = ["Bojonegoro", "Lamongan", "Nganjuk", "Ngawi", "Tuban"]


def _log(msg: str) -> None:
    print(f"[update_weekly] {msg}", flush=True)


def last_observed_date() -> date | None:
    if not RAW.exists():
        return None
    col = pd.read_parquet(RAW, columns=["time"])["time"]
    return pd.to_datetime(col).max().date()


def _run(cmd: list[str]) -> None:
    _log("$ " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        raise SystemExit(f"perintah gagal ({result.returncode}): {' '.join(cmd)}")


def refresh_raw(since: date, until: date) -> None:
    """Unduh delta per node sampai `until` (inklusif -> +1 hari, Open-Meteo eksklusif)."""
    _run([
        PY, "-c",
        "from src.data.ingest import main; main("
        f"start_date={since.isoformat()!r}, end_date={(until + timedelta(days=1)).isoformat()!r},"
        "resume_existing=True, strict_coverage=True)",
    ])


def rebuild_processed() -> None:
    _run([PY, "-c", "from src.data.preprocess import preprocess_pipeline; preprocess_pipeline()"])


def regenerate_forecast() -> dict:
    """Inferensi 30 hari dari checkpoint terbaik — model tidak dilatih ulang."""
    import torch

    torch.set_float32_matmul_precision("medium")
    from src.evaluation.inference import build_bundle

    bundle = build_bundle()
    data = bundle.data
    payload = {
        "checkpoint": Path(bundle.checkpoint_path).name,
        "last_observed": str(bundle.last_observed_time.date()),
        "observed_days": OBS_DAYS,
        "forecast_days": FU_DAYS,
        "severity_thresholds": {"moderate": -1.0, "severe": -1.5, "extreme": -2.0},
        "cities": {},
    }
    for city in CITIES:
        entity = bundle._entity_for(city)
        hist = data[data["super_node_id"].astype(str) == entity].sort_values("time").tail(OBS_DAYS)
        forecast = bundle.forecast(city, FU_DAYS)
        payload["cities"][city] = {
            "entity": entity,
            "observed": {
                "dates": [pd.Timestamp(t).date().isoformat() for t in hist["time"]],
                "spei": [round(float(v), 4) for v in hist["SPEI_3"]],
            },
            "forecast": {
                "dates": forecast["dates"],
                "p10": [round(v, 4) for v in forecast["p10"]],
                "p50": [round(v, 4) for v in forecast["p50"]],
                "p90": [round(v, 4) for v in forecast["p90"]],
            },
        }
        _log(f"{city:12} {payload['cities'][city]['forecast']['dates'][0]} .. "
             f"{payload['cities'][city]['forecast']['dates'][-1]}  p50_akhir="
             f"{payload['cities'][city]['forecast']['p50'][-1]:.3f}")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="Segarkan data + artefak prakiraan 30 hari (tanpa retrain)")
    ap.add_argument("--since", help="tanggal mulai delta (YYYY-MM-DD); default: setelah baris terakhir raw")
    ap.add_argument("--until", help="tanggal akhir delta (YYYY-MM-DD); default: kemarin")
    ap.add_argument("--dry-run", action="store_true", help="hitung rentang dan berhenti, tanpa mengunduh")
    args = ap.parse_args()

    until = date.fromisoformat(args.until) if args.until else date.today() - timedelta(days=1)
    if args.since:
        since = date.fromisoformat(args.since)
    else:
        last = last_observed_date()
        if last is None:
            raise SystemExit("raw dataset tidak ditemukan; jalankan ingest penuh dulu")
        since = last + timedelta(days=1)

    if since > until:
        _log(f"tidak ada delta: data terakhir >= {until.isoformat()} (since={since.isoformat()}). Selesai.")
        return

    _log(f"delta {since.isoformat()} .. {until.isoformat()} ({(until - since).days + 1} hari)")
    _log(f"checkpoint beku (tidak dilatih ulang); artefak -> {ARTIFACT.relative_to(ROOT)}")
    if args.dry_run:
        _log("dry-run: berhenti tanpa mengunduh.")
        return

    refresh_raw(since, until)
    rebuild_processed()
    payload = regenerate_forecast()
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    _log(f"ditulis: {ARTIFACT.relative_to(ROOT)} ({ARTIFACT.stat().st_size} byte), "
         f"observasi sampai {payload['last_observed']}")


if __name__ == "__main__":
    main()