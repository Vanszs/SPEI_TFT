"""Pembaruan data mingguan untuk inference (bukan retraining).

Model TFT dibekukan pada checkpoint terbaik. Prakiraan dimulai setelah cutoff
siklus (akhir bulan sebelumnya), bukan setelah baris terakhir parquet. Yang
disearkan tiap bulan adalah DATA, bukan bobot model:

Operasionalnya dijadwalkan bulanan dengan lag 1 bulan: pada tanggal 1, data
dipotong ke akhir bulan sebelumnya (cutoff) dan model memprediksi bulan itu.

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
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from datetime import timezone
from pathlib import Path

import pandas as pd

from src.data.spei import SEVERITY_THRESHOLDS
from scripts.forecast_history import atomic_write_json, build_history

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/weather_history_east_java.parquet"
PROCESSED = ROOT / "data/processed/spei_dataset.parquet"
ARTIFACT = ROOT / "frontend/public/forecast_30d.json"
PY = sys.executable

OBS_DAYS = 30
FU_DAYS = 30
# Arsip ERA5-Land/Open-Meteo tertinggal ~5-7 hari. Jangan pernah memakai data
# yang belum diterbitkan: batas default = hari ini - lag.
FETCH_LAG_DAYS = int(os.getenv("DROUGHT_FETCH_LAG_DAYS", "7"))
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


def cycle_anchor(today: date | None = None) -> date:
    """Tanggal 1 dari bulan sebelumnya.

    Aturan project: lag data 1 bulan. Pada 4 Nov, anchor = 1 Okt; input 3 bulan
    (Jul-Sep), output 1 bulan (Okt). Anchor hanya berubah pada tanggal 1.
    """
    today = today or date.today()
    year = today.year - (1 if today.month == 1 else 0)
    month = 12 if today.month == 1 else today.month - 1
    return date(year, month, 1)


def regenerate_forecast(anchor: date | None = None) -> dict:
    """Inferensi 30 hari dari checkpoint terbaik — model tidak dilatih ulang."""
    import torch

    torch.set_float32_matmul_precision("medium")
    from src.evaluation.inference import build_bundle

    bundle = build_bundle()
    data = bundle.data
    anchor = anchor or cycle_anchor()
    cutoff = anchor - timedelta(days=1)
    payload = {
        "anchor": anchor.isoformat(),
        "cutoff": cutoff.isoformat(),
        "checkpoint": Path(bundle.checkpoint_path).name,
        "last_observed": cutoff.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_delay_days": (date.today() - cutoff).days,
        "observed_days": OBS_DAYS,
        "forecast_days": FU_DAYS,
        "severity_thresholds": dict(SEVERITY_THRESHOLDS),
        "cities": {},
    }
    for city in sorted(data["city_id"].astype(str).unique()):
        entity = bundle._entity_for(city)
        loc = data[data["super_node_id"].astype(str) == entity].sort_values("time")
        hist = loc[loc["time"] <= pd.Timestamp(cutoff)].tail(OBS_DAYS)
        forecast = bundle.forecast_as_of(city, cutoff, FU_DAYS)
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


def _acquire_lock():
    """Cegah dua pembaruan berjalan bersamaan (cron + PM2 scheduler + manual)."""
    import fcntl

    lock_path = ROOT / "logs/update_weekly.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _log("pembaruan lain sedang berjalan; keluar tanpa mengubah apa pun.")
        raise SystemExit(0)
    return handle


def main() -> None:
    ap = argparse.ArgumentParser(description="Segarkan data + artefak prakiraan 30 hari (tanpa retrain)")
    ap.add_argument("--since", help="tanggal mulai delta (YYYY-MM-DD); default: setelah baris terakhir raw")
    ap.add_argument("--until", help="tanggal akhir delta (YYYY-MM-DD); default: kemarin")
    ap.add_argument("--dry-run", action="store_true", help="hitung rentang dan berhenti, tanpa mengunduh")
    args = ap.parse_args()

    until = date.fromisoformat(args.until) if args.until else date.today() - timedelta(days=FETCH_LAG_DAYS)
    if args.since:
        since = date.fromisoformat(args.since)
    else:
        last = last_observed_date()
        if last is None:
            raise SystemExit("raw dataset tidak ditemukan; jalankan ingest penuh dulu")
        since = last + timedelta(days=1)

    if args.dry_run:
        if since > until:
            _log(f"tidak ada delta: data terakhir >= {until.isoformat()}.")
        else:
            _log(f"delta {since.isoformat()} .. {until.isoformat()} ({(until - since).days + 1} hari)")
        _log("dry-run: berhenti tanpa mengunduh.")
        return

    lock = _acquire_lock()

    if since > until:
        _log(f"tidak ada delta: data terakhir >= {until.isoformat()} (since={since.isoformat()}).")
        raw_last = last_observed_date()
        artifact_lags = True
        expected_cutoff = (cycle_anchor() - timedelta(days=1)).isoformat()
        if ARTIFACT.exists():
            try:
                previous = json.loads(ARTIFACT.read_text(encoding="utf-8"))
                artifact_lags = previous.get("last_observed") != expected_cutoff
            except (json.JSONDecodeError, OSError):
                pass
        if artifact_lags and not args.dry_run:
            _log("artefak tertinggal dari data mentah; regenerasi prakiraan + history")
            payload = regenerate_forecast()
            atomic_write_json(ARTIFACT, payload)
            build_history(ARTIFACT)
        return

    _log(f"delta {since.isoformat()} .. {until.isoformat()} ({(until - since).days + 1} hari)")
    _log(f"checkpoint beku (tidak dilatih ulang); artefak -> {ARTIFACT.relative_to(ROOT)}")

    refresh_raw(since, until)
    rebuild_processed()
    payload = regenerate_forecast()
    _log(f"usia data: {payload['data_delay_days']} hari")
    atomic_write_json(ARTIFACT, payload)
    _log(f"ditulis: {ARTIFACT.relative_to(ROOT)} ({ARTIFACT.stat().st_size} byte), "
         f"observasi sampai {payload['last_observed']}")
    try:
        build_history(ARTIFACT)
    except Exception as exc:
        _log(f"gagal membangun history; forecast tetap tersimpan: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
