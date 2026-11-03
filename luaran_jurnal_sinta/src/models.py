"""Builder model TFT dan baseline LSTM + loader checkpoint."""

from __future__ import annotations

from typing import Any

from pytorch_forecasting import TemporalFusionTransformer
from pytorch_forecasting.metrics import MAE, QuantileLoss
from pytorch_forecasting.models import RecurrentNetwork

MODEL_NAMES = ("tft", "lstm")


def build_model(name: str, training_dataset, cfg: dict[str, Any]):
    name = name.lower()
    if name not in MODEL_NAMES:
        raise ValueError(f"Model '{name}' tidak dikenal. Pilihan: {MODEL_NAMES}")

    model_cfg = cfg["model"]
    quantiles = [float(q) for q in model_cfg["quantiles"]]
    if name == "tft" and quantiles != [0.1, 0.5, 0.9]:
        raise ValueError(
            "Metrik PICP80/MPIW mengasumsikan quantiles [0.1, 0.5, 0.9]; "
            f"config berisi {quantiles}."
        )
    common = {
        "learning_rate": float(model_cfg["learning_rate"]),
        "weight_decay": float(model_cfg["weight_decay"]),
        "reduce_on_plateau_patience": int(model_cfg.get("lr_patience", 4)),
        "log_interval": -1,
    }

    if name == "tft":
        return TemporalFusionTransformer.from_dataset(
            training_dataset,
            hidden_size=int(model_cfg["hidden_size"]),
            attention_head_size=int(model_cfg["attention_head_size"]),
            dropout=float(model_cfg["dropout"]),
            hidden_continuous_size=int(model_cfg["hidden_continuous_size"]),
            output_size=len(quantiles),
            loss=QuantileLoss(quantiles=quantiles),
            **common,
        )

    return RecurrentNetwork.from_dataset(
        training_dataset,
        cell_type="LSTM",
        hidden_size=int(model_cfg["hidden_size"]),
        rnn_layers=int(model_cfg.get("rnn_layers", 2)),
        dropout=float(model_cfg["dropout"]),
        # RecurrentNetwork tidak mendukung QuantileLoss; baseline = point forecast MAE.
        loss=MAE(),
        **common,
    )


def load_checkpoint(name: str, checkpoint_path: str, map_location: str = "cpu"):
    cls = TemporalFusionTransformer if name.lower() == "tft" else RecurrentNetwork
    # weights_only=False needed because dataset_parameters menyimpan normalizer sklearn.
    return cls.load_from_checkpoint(
        checkpoint_path,
        map_location=map_location,
        weights_only=False,
    )
