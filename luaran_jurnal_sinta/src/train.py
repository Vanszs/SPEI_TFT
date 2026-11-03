"""Latih TFT (atau baseline LSTM) pada tabel harian Bromo."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import lightning as L
import pandas as pd
import pytorch_forecasting
import torch
from lightning.pytorch.callbacks import Callback, EarlyStopping, ModelCheckpoint

from src.config import load_config, resolve
from src.dataset import build_eval_dataset, build_training_dataset, dataloader
from src.models import build_model


class EpochSummary(Callback):
    def on_train_epoch_start(self, trainer, pl_module):
        if not trainer.sanity_checking:
            self._start = time.time()

    def on_validation_epoch_end(self, trainer, pl_module):
        if trainer.sanity_checking:
            return
        metrics = trainer.callback_metrics
        train_loss = metrics.get("train_loss_epoch", metrics.get("train_loss"))
        if train_loss is None or "val_loss" not in metrics:
            return
        lr = trainer.optimizers[0].param_groups[0]["lr"] if trainer.optimizers else float("nan")
        elapsed = time.time() - getattr(self, "_start", time.time())
        print(
            f"  epoch {trainer.current_epoch:>3} | "
            f"train={float(train_loss):.4f} | "
            f"val={float(metrics['val_loss']):.4f} | lr={lr:.2e} | {elapsed:.0f}s"
        )


def _precision(model_name: str, accelerator: str, requested: str) -> str:
    if accelerator != "gpu":
        return "32-true"
    if model_name == "lstm":
        # RecurrentNetwork tidak kompatibel dengan autocast bf16/fp16.
        return "32-true"
    if requested == "bf16-mixed" and not torch.cuda.is_bf16_supported():
        print("[warn] GPU tidak mendukung bf16; fallback precision=32-true")
        return "32-true"
    return requested


def _data_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train(cfg: dict, model_name: str, max_epochs: int | None = None, seed: int | None = None,
          run_id: str | None = None, cpu: bool = False) -> str:
    model_cfg = cfg["model"]
    seed = int(seed if seed is not None else model_cfg["seed"])
    epochs = int(max_epochs if max_epochs is not None else model_cfg["max_epochs"])
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    L.seed_everything(seed, workers=True)

    data_path = resolve(cfg, cfg["data"]["processed_dir"]) / "bromo_daily.parquet"
    if not data_path.exists():
        raise FileNotFoundError(f"{data_path} tidak ada. Jalankan: python -m src.preprocess")
    data = pd.read_parquet(data_path)

    print(
        f"[data] {len(data)} hari | train={int((data.split == 'train').sum())} "
        f"| val={int((data.split == 'val').sum())} | test={int((data.split == 'test').sum())}"
    )
    include_past = model_name == "tft"
    training_dataset = build_training_dataset(data, cfg, include_past_covariates=include_past)
    val_dataset = build_eval_dataset(training_dataset, data, "val", cfg)

    train_loader = dataloader(training_dataset, cfg, train=True)
    val_loader = dataloader(val_dataset, cfg, train=False)

    model = build_model(model_name, training_dataset, cfg)

    logs_dir = resolve(cfg, cfg["paths"]["logs"])
    checkpoint_dir = logs_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    callbacks = [
        EarlyStopping(
            monitor="val_loss",
            min_delta=1e-4,
            patience=int(model_cfg["patience"]),
            mode="min",
            verbose=True,
        ),
        ModelCheckpoint(
            dirpath=checkpoint_dir,
            filename=f"{model_name}-{run_id}-{{epoch:02d}}-{{val_loss:.4f}}",
            monitor="val_loss",
            mode="min",
            save_top_k=1,
            verbose=False,
        ),
        EpochSummary(),
    ]

    accelerator = "cpu" if cpu or not torch.cuda.is_available() else "gpu"
    precision = _precision(model_name, accelerator, str(model_cfg.get("precision", "bf16-mixed")))
    if accelerator == "gpu" and precision != "32-true":
        torch.set_float32_matmul_precision("medium")

    trainer = L.Trainer(
        max_epochs=epochs,
        accelerator=accelerator,
        devices=1,
        precision=precision,
        gradient_clip_val=float(model_cfg.get("gradient_clip_val", 0.0)),
        deterministic="warn",
        callbacks=callbacks,
        enable_progress_bar=False,
        enable_model_summary=True,
        logger=False,
        default_root_dir=str(logs_dir),
    )

    print(f"[train] model={model_name} | accelerator={accelerator} | precision={precision}")
    trainer.fit(model, train_dataloaders=train_loader, val_dataloaders=val_loader)

    best_path = str(trainer.checkpoint_callback.best_model_path)
    run_config = {
        "model": model_name,
        "run_id": run_id,
        "seed": seed,
        "max_epochs": epochs,
        "accelerator": accelerator,
        "precision": precision,
        "data_path": str(data_path),
        "data_sha256": _data_hash(data_path),
        "rows": int(len(data)),
        "include_past_covariates": include_past,
        "versions": {
            "torch": torch.__version__,
            "lightning": L.__version__,
            "pytorch_forecasting": pytorch_forecasting.__version__,
        },
        "config": {key: value for key, value in cfg.items() if not key.startswith("_")},
        "best_model_path": best_path,
    }
    config_out = logs_dir / f"run_config_{model_name}.json"
    config_out.write_text(json.dumps(run_config, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[ok] checkpoint: {best_path}")
    print(f"[ok] run config: {config_out}")
    return best_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Latih TFT/LSTM untuk Bromo ERA5-Land")
    parser.add_argument("--config", default=None)
    parser.add_argument("--model", choices=("tft", "lstm"), default="tft")
    parser.add_argument("--max-epochs", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    train(
        cfg,
        args.model,
        max_epochs=args.max_epochs,
        seed=args.seed,
        run_id=args.run_id,
        cpu=args.cpu,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
