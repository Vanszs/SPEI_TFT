"""Penjadwal bulanan untuk deployment PM2.

Menggantikan cron: satu proses kecil yang tidur sampai tanggal 1 pukul 05:15,
lalu menjalankan `scripts.update_weekly` sebagai subprocess. Dijalankan PM2
dengan instances: 1 dan autorestart: true, jadi jadwalnya ikut hidup/mati
bersama deployment web.

Sengaja TIDAK ditaruh di proses FastAPI: uvicorn berjalan dengan 2 worker,
sehingga penjadwal in-process akan berjalan dua kali dan rebutan file data.
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "logs/scheduler_state.json"
RUN_HOUR = 5
RUN_MINUTE = 15


def next_run(now: datetime | None = None) -> datetime:
    """Tanggal 1 bulan berikutnya pukul 05:15 (waktu lokal server)."""
    current = now or datetime.now()
    target = current.replace(day=1, hour=RUN_HOUR, minute=RUN_MINUTE, second=0, microsecond=0)
    if target <= current:
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        target = target.replace(year=year, month=month)
    return target


def scheduled_slot(now: datetime) -> datetime:
    """Jadwal terakhir yang seharusnya sudah dijalankan (tanggal 1 05:15)."""
    slot = now.replace(day=1, hour=RUN_HOUR, minute=RUN_MINUTE, second=0, microsecond=0)
    if slot <= now:
        return slot
    year = now.year - (1 if now.month == 1 else 0)
    month = 12 if now.month == 1 else now.month - 1
    return slot.replace(year=year, month=month)


def last_completed() -> datetime | None:
    try:
        return datetime.fromisoformat(json.loads(STATE_PATH.read_text(encoding="utf-8"))["last_completed"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def mark_completed(slot: datetime) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"last_completed": slot.isoformat()}), encoding="utf-8")


def run_once() -> int:
    print(f"[scheduler] mulai {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
    result = subprocess.run([sys.executable, "-m", "scripts.update_weekly"], cwd=ROOT)
    print(f"[scheduler] selesai rc={result.returncode} {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
    return result.returncode


def main() -> None:
    while True:
        now = datetime.now()
        slot = scheduled_slot(now)
        last = last_completed()
        if last is None or last < slot:
            # Catch-up: server mati/restart saat jadwal tetap dijalankan sekali.
            print(f"[scheduler] catch-up untuk {slot:%Y-%m-%d %H:%M}", flush=True)
            try:
                run_once()
                mark_completed(slot)
            except Exception as exc:
                print(f"[scheduler] gagal: {exc}", flush=True)
        target = next_run()
        print(f"[scheduler] tidur sampai {target:%Y-%m-%d %H:%M}", flush=True)
        while True:
            remaining = (target - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            # Potong tidur per 5 menit: aman terhadap perubahan jam sistem.
            time.sleep(min(remaining, 300))
        try:
            run_once()
            mark_completed(scheduled_slot(datetime.now()))
        except Exception as exc:  # jangan biarkan scheduler mati karena satu kegagalan
            print(f"[scheduler] gagal: {exc}", flush=True)


if __name__ == "__main__":
    main()
