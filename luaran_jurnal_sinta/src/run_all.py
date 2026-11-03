"""Jalankan seluruh pipeline: acquire -> preprocess -> EDA -> train -> evaluate -> interpret."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from src.config import ROOT


def run(module: str, *args: str) -> None:
    command = [sys.executable, "-m", module, *args]
    print(f"\n$ {' '.join(command)}", flush=True)
    try:
        subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"[stop] {module} gagal (exit {exc.returncode})") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline lengkap luaran jurnal SINTA")
    parser.add_argument("--config", default=None)
    parser.add_argument("--skip-acquire", action="store_true")
    parser.add_argument("--skip-baseline", action="store_true", help="Lewati training/evaluasi LSTM")
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--max-epochs", type=int, default=None)
    args = parser.parse_args(argv)

    cfg_path = str(Path(args.config).resolve()) if args.config else str(ROOT / "configs/bromo.yaml")
    config_args = ("--config", cfg_path)
    cpu_args = ("--cpu",) if args.cpu else ()
    epoch_args = ("--max-epochs", str(args.max_epochs)) if args.max_epochs else ()

    if not args.skip_acquire:
        run("src.acquire_era5", *config_args)
    run("src.preprocess", *config_args)
    run("src.eda", *config_args)

    run("src.train", *config_args, "--model", "tft", *cpu_args, *epoch_args)
    run("src.evaluate", *config_args, "--model", "tft")
    run("src.interpret", *config_args)

    if not args.skip_baseline:
        run("src.train", *config_args, "--model", "lstm", *cpu_args, *epoch_args)
        run("src.evaluate", *config_args, "--model", "lstm")
        run("src.compare", *config_args)

    print("\n[done] cek folder results/ untuk tabel dan gambar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
