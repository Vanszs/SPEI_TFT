"""Canonical NumPy point-forecast metrics for the evaluation layer."""
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def point_metrics(actual, predicted) -> dict:
    """RMSE, MAE, R2, Pearson r, bias and sample count over finite pairs only.

    Single source of truth; every key is always present so downstream consumers
    (baselines, evaluate.py, full_evaluation.py) share one contract.
    """
    act = np.asarray(actual, dtype=np.float64).reshape(-1)
    pred = np.asarray(predicted, dtype=np.float64).reshape(-1)
    mask = np.isfinite(act) & np.isfinite(pred)
    a, p = act[mask], pred[mask]
    if a.size < 2:
        return {"rmse": None, "mae": None, "r2": None, "pearson_r": None,
                "bias": None, "n_samples": int(a.size)}
    pearson = float(np.corrcoef(a, p)[0, 1]) if (np.std(a) > 1e-9 and np.std(p) > 1e-9) else None
    return {
        "rmse": float(np.sqrt(mean_squared_error(a, p))),
        "mae": float(mean_absolute_error(a, p)),
        "r2": float(r2_score(a, p)),
        "pearson_r": pearson,
        "bias": float(np.mean(p - a)),
        "n_samples": int(a.size),
    }
