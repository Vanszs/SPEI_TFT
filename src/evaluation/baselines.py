"""
baselines.py
============
BAB III §3.8.1 comparison baseline models for SPEI-3 multi-horizon forecasting.
Models implemented:
1. Multi-horizon XGBoost (direct multi-output regression across 30 horizons).
2. Hybrid ARIMA-LSTM (linear ARIMA component + PyTorch LSTM on residuals,
   iterative multi-step forecasting across 30 horizons).

Identical setup to TFT:
- Target: SPEI_3
- Group key: super_node_id (5 entities)
- Chronological split: train (year < 2023), val (year == 2023), test (year >= 2024)
- Multi-horizon: t+1 .. t+30 (30 steps)
- Point forecast metrics on test set: RMSE, MAE, R2, Pearson r, n_samples
"""

import json
import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Check available baseline dependencies
try:
    from statsmodels.tsa.arima.model import ARIMA

    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False

try:
    import xgboost as xgb

    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    import torch
    import torch.nn as nn

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


RAW_FEATURE_COLS = [
    "SPEI_3",
    "SPEI_3_diff",
    "water_deficit",
    "precipitation_log",
    "et0_fao_evapotranspiration",
    "soil_moisture",
    "temperature_2m_max",
    "temperature_2m_min",
    "relative_humidity_2m_mean",
    "shortwave_radiation_sum",
    "wind_speed_10m_mean",
    "month_sin",
    "month_cos",
    "elevation",
    "lat",
    "lon",
]


from src.evaluation.point_metrics import point_metrics as _point_metrics


def _calc_metrics(actual: np.ndarray, pred: np.ndarray) -> Dict[str, Any]:
    """Thin alias of the canonical point-metric helper (keeps the public name)."""
    return _point_metrics(actual, pred)


def _create_tabular_samples(
    data: pd.DataFrame, lookback: int = 90, horizon: int = 30
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Construct multi-horizon tabular samples from time-ordered super_node data.
    Encoder lookback = 90 (matches TFT max encoder length).
    Decoder horizon = 30 (predicts t+1 .. t+30).
    """
    n_rows = len(data)
    available_cols = [c for c in RAW_FEATURE_COLS if c in data.columns]
    raw_mat = data[available_cols].values
    spei = data["SPEI_3"].values
    deficit = data["water_deficit"].values if "water_deficit" in data.columns else None
    precip = data["precipitation_log"].values if "precipitation_log" in data.columns else None
    sm = data["soil_moisture"].values if "soil_moisture" in data.columns else None
    temp = data["temperature_2m_max"].values if "temperature_2m_max" in data.columns else None

    X_list: List[np.ndarray] = []
    Y_list: List[np.ndarray] = []

    for i in range(lookback, n_rows - horizon + 1):
        feat_cur = raw_mat[i - 1]
        spei_window = spei[i - lookback : i]

        # Multi-scale lag features
        lags = [
            spei[i - 1],
            spei[i - 2],
            spei[i - 3],
            spei[i - 7],
            spei[i - 14],
            spei[i - 30],
            spei[i - 60],
            spei[i - 90],
        ]

        # Rolling statistics over past windows
        roll7_mean = float(np.mean(spei[i - 7 : i]))
        roll30_mean = float(np.mean(spei[i - 30 : i]))
        roll90_mean = float(np.mean(spei_window))
        roll7_std = float(np.std(spei[i - 7 : i]))
        roll30_std = float(np.std(spei[i - 30 : i]))

        roll_extras = []
        if deficit is not None:
            roll_extras.append(float(np.mean(deficit[i - 30 : i])))
        if precip is not None:
            roll_extras.append(float(np.mean(precip[i - 30 : i])))
        if sm is not None:
            roll_extras.append(float(np.mean(sm[i - 30 : i])))
        if temp is not None:
            roll_extras.append(float(np.mean(temp[i - 30 : i])))

        row_feat = np.concatenate(
            [
                feat_cur,
                lags,
                [roll7_mean, roll30_mean, roll90_mean, roll7_std, roll30_std],
                roll_extras,
            ]
        )
        X_list.append(row_feat)
        Y_list.append(spei[i : i + horizon])

    return np.array(X_list, dtype=np.float32), np.array(Y_list, dtype=np.float32)


def fit_predict_xgboost(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    lookback: int = 90,
    horizon: int = 30,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Fit direct multi-horizon XGBoost on train_df (<2023) and predict on test_df (>=2024).
    Returns (actuals, predictions) matrices of shape (n_test_windows, horizon).
    """
    if not HAS_XGBOOST:
        raise ImportError("xgboost is not installed.")

    X_train, Y_train = _create_tabular_samples(train_df, lookback=lookback, horizon=horizon)
    X_test, Y_test = _create_tabular_samples(test_df, lookback=lookback, horizon=horizon)

    if len(X_train) == 0 or len(X_test) == 0:
        raise ValueError(
            f"Insufficient samples to construct windows (X_tr={len(X_train)}, X_te={len(X_test)})."
        )

    model = xgb.XGBRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        tree_method="hist",
        random_state=42,
        n_jobs=min(4, os.cpu_count() or 1),
    )
    model.fit(X_train, Y_train)
    preds = model.predict(X_test)
    return Y_test, preds


if HAS_TORCH:

    class ResidualLSTM(nn.Module):
        """Compact PyTorch LSTM model for fitting time-series residuals."""

        def __init__(self, input_size: int = 1, hidden_size: int = 16, num_layers: int = 1):
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden_size, num_layers=num_layers, batch_first=True)
            self.fc = nn.Linear(hidden_size, 1)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :])

else:
    ResidualLSTM = None  # type: ignore


def fit_predict_arima_lstm(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    lookback: int = 90,
    horizon: int = 30,
    order: Tuple[int, int, int] = (2, 1, 0),
    lstm_lookback: int = 14,
    epochs: int = 10,
    allow_ar_fallback: bool = False,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Fit hybrid ARIMA-LSTM per super-node:
    1. Linear component: ARIMA(order) on train series.
    2. Nonlinear component: PyTorch LSTM trained on ARIMA residuals.
    3. Multi-horizon forecast: iterative rolling prediction over horizon steps.

    If statsmodels is not installed and allow_ar_fallback=False, returns None.
    If allow_ar_fallback=True, fits differenced AR(p) linear component via OLS.
    """
    if not HAS_TORCH:
        return None

    y_train = train_df["SPEI_3"].values.astype(np.float64)
    y_test = test_df["SPEI_3"].values.astype(np.float64)

    if HAS_STATSMODELS:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            arima_model = ARIMA(y_train, order=order)
            arima_fit = arima_model.fit()
            linear_train_fit = arima_fit.fittedvalues
            residuals_train = y_train - linear_train_fit

            # Real ARIMA parameters for iterative forecast: AR coefficients and
            # differencing order from the fitted model (no heuristic).
            names = list(getattr(arima_fit, "param_names", []))
            ar_params = np.asarray(
                [
                    float(arima_fit.params[names.index(f"ar.L{i}")])
                    if f"ar.L{i}" in names
                    else 0.0
                    for i in range(1, order[0] + 1)
                ],
                dtype=float,
            )
            d = order[1]
            ar_lags = len(ar_params)
    elif allow_ar_fallback:
        # Fallback linear AR(p) on differenced series using numpy OLS
        d = 1
        ar_lags = 2
        diff_tr = np.diff(y_train)
        X_ar = np.column_stack([diff_tr[1:-1], diff_tr[:-2]])
        Y_ar = diff_tr[2:]
        phi, _, _, _ = np.linalg.lstsq(X_ar, Y_ar, rcond=None)
        diff_pred = np.dot(X_ar, phi)
        residuals_train = diff_tr[2:] - diff_pred
    else:
        # Per contract: do not fake ARIMA when statsmodels is missing
        return None

    # Train PyTorch ResidualLSTM
    torch.manual_seed(42)
    lstm = ResidualLSTM(input_size=1, hidden_size=16, num_layers=1)
    optimizer = torch.optim.Adam(lstm.parameters(), lr=0.01)
    criterion = nn.MSELoss()

    res_clean = np.nan_to_num(residuals_train, nan=0.0)
    X_lstm, Y_lstm = [], []
    for idx in range(lstm_lookback, len(res_clean)):
        X_lstm.append(res_clean[idx - lstm_lookback : idx].reshape(-1, 1))
        Y_lstm.append(res_clean[idx])

    if len(X_lstm) > 0:
        X_tensor = torch.tensor(np.array(X_lstm), dtype=torch.float32)
        Y_tensor = torch.tensor(np.array(Y_lstm).reshape(-1, 1), dtype=torch.float32)

        lstm.train()
        batch_size = 64
        dataset_len = len(X_tensor)
        for _ in range(epochs):
            permutation = torch.randperm(dataset_len)
            for b_start in range(0, dataset_len, batch_size):
                b_idx = permutation[b_start : b_start + batch_size]
                optimizer.zero_grad()
                pred_res = lstm(X_tensor[b_idx])
                loss = criterion(pred_res, Y_tensor[b_idx])
                loss.backward()
                optimizer.step()
    lstm.eval()

    # Multi-horizon iterative forecast on test windows
    n_test = len(y_test)
    act_windows, pred_windows = [], []

    for i in range(lookback, n_test - horizon + 1):
        actual_h = y_test[i : i + horizon]
        hist_y = list(y_test[i - lookback : i])
        hist_res = list(res_clean[-lstm_lookback:])

        pred_h = []
        for h in range(horizon):
            # 1. Linear forecast step: proper ARIMA recursion.
            if HAS_STATSMODELS:
                if d == 1:
                    # Forecast the differenced series with fitted AR coefficients,
                    # then re-integrate: y_t = y_{t-1} + ar @ diff_lags.
                    diffs = np.diff(hist_y)
                    if len(diffs) >= ar_lags and ar_lags > 0:
                        delta = float(np.dot(ar_params, diffs[-ar_lags:][::-1]))
                    else:
                        delta = 0.0
                    l_pred = hist_y[-1] + delta
                else:
                    l_pred = hist_y[-1]
            elif allow_ar_fallback:
                last_diffs = np.array([hist_y[-1] - hist_y[-2], hist_y[-2] - hist_y[-3]])
                delta_linear = float(np.dot(last_diffs, phi))
                l_pred = hist_y[-1] + delta_linear
            else:
                l_pred = hist_y[-1]

            # 2. Residual forecast step from LSTM
            inp_res = torch.tensor(
                np.array(hist_res[-lstm_lookback:]).reshape(1, lstm_lookback, 1),
                dtype=torch.float32,
            )
            with torch.no_grad():
                r_pred = float(lstm(inp_res).item())

            # 3. Hybrid addition
            y_hat = float(l_pred + r_pred)
            pred_h.append(y_hat)

            # Update rolling sequence
            hist_y.append(y_hat)
            hist_res.append(r_pred)

        act_windows.append(actual_h)
        pred_windows.append(pred_h)

    return np.array(act_windows, dtype=np.float32), np.array(pred_windows, dtype=np.float32)


def run_baselines(
    data_path: str = "data/processed/spei_dataset.parquet",
    out_json: str = "results/bab3_baseline_metrics.json",
    allow_ar_fallback: bool = False,
) -> Dict[str, Any]:
    """
    Fits comparison baselines per super_node, evaluates on test split, and writes metrics JSON.

    Parameters:
    - data_path: Path to spei_dataset.parquet
    - out_json: Output path for bab3_baseline_metrics.json
    - allow_ar_fallback: If True and statsmodels is missing, uses numpy OLS AR(2,1,0) for linear stage.
                         If False and statsmodels is missing, records null metrics without faking.

    Returns dict with keys 'arima_lstm' and 'xgboost', each containing:
    {rmse, mae, r2, pearson_r, n_samples, note}.
    """
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Processed dataset not found: {data_path}")

    data = pd.read_parquet(data_path)
    data["time"] = pd.to_datetime(data["time"])
    data["year"] = data["time"].dt.year

    if "super_node_id" not in data.columns:
        raise ValueError("Dataset missing required grouping column 'super_node_id'.")

    # Chronological splits
    train_data = data[data.year < 2023].copy()
    test_data = data[data.year >= 2024].copy()

    entities = sorted(data["super_node_id"].astype(str).unique().tolist())
    if not entities:
        raise ValueError("No super_node entities found in dataset.")

    # -------------------------------------------------------------
    # 1. XGBoost Baseline
    # -------------------------------------------------------------
    xgb_metrics: Dict[str, Any]
    if HAS_XGBOOST:
        xgb_acts_all, xgb_preds_all = [], []
        xgb_per_node = {}

        for ent in entities:
            ent_train = train_data[train_data.super_node_id == ent].sort_values("time").copy()
            ent_test = test_data[test_data.super_node_id == ent].sort_values("time").copy()

            Y_te, Y_pred = fit_predict_xgboost(ent_train, ent_test, lookback=90, horizon=30)
            xgb_acts_all.append(Y_te)
            xgb_preds_all.append(Y_pred)
            xgb_per_node[ent] = _calc_metrics(Y_te, Y_pred)

        acts_mat = np.concatenate(xgb_acts_all, axis=0)
        preds_mat = np.concatenate(xgb_preds_all, axis=0)
        overall_xgb = _calc_metrics(acts_mat, preds_mat)

        xgb_metrics = {
            "rmse": overall_xgb["rmse"],
            "mae": overall_xgb["mae"],
            "r2": overall_xgb["r2"],
            "pearson_r": overall_xgb["pearson_r"],
            "n_samples": overall_xgb["n_samples"],
            "note": (
                "Direct multi-horizon XGBoost (tree_method='hist') fitted per super_node "
                "on train (year < 2023) and evaluated on test (year >= 2024) across 30 horizons."
            ),
            "per_super_node": xgb_per_node,
        }
    else:
        xgb_metrics = {
            "rmse": None,
            "mae": None,
            "r2": None,
            "pearson_r": None,
            "n_samples": 0,
            "note": "xgboost is missing from the environment; model not fit.",
        }

    # -------------------------------------------------------------
    # 2. Hybrid ARIMA-LSTM Baseline
    # -------------------------------------------------------------
    arima_metrics: Dict[str, Any]
    if HAS_STATSMODELS or (allow_ar_fallback and HAS_TORCH):
        arima_acts_all, arima_preds_all = [], []
        arima_per_node = {}
        fit_failed = False

        for ent in entities:
            ent_train = train_data[train_data.super_node_id == ent].sort_values("time").copy()
            ent_test = test_data[test_data.super_node_id == ent].sort_values("time").copy()

            res = fit_predict_arima_lstm(
                ent_train,
                ent_test,
                lookback=90,
                horizon=30,
                order=(2, 1, 0),
                allow_ar_fallback=allow_ar_fallback,
            )
            if res is None:
                fit_failed = True
                break
            Y_te, Y_pred = res
            arima_acts_all.append(Y_te)
            arima_preds_all.append(Y_pred)
            arima_per_node[ent] = _calc_metrics(Y_te, Y_pred)

        if not fit_failed and arima_acts_all:
            acts_arima_mat = np.concatenate(arima_acts_all, axis=0)
            preds_arima_mat = np.concatenate(arima_preds_all, axis=0)
            overall_arima = _calc_metrics(acts_arima_mat, preds_arima_mat)

            impl_note = (
                "Hybrid statsmodels ARIMA(2,1,0) + PyTorch LSTM residual model"
                if HAS_STATSMODELS
                else "Hybrid numpy OLS AR(2,1,0) + PyTorch LSTM residual model (statsmodels fallback)"
            )
            arima_metrics = {
                "rmse": overall_arima["rmse"],
                "mae": overall_arima["mae"],
                "r2": overall_arima["r2"],
                "pearson_r": overall_arima["pearson_r"],
                "n_samples": overall_arima["n_samples"],
                "note": (
                    f"{impl_note} with iterative multi-step forecasting across 30 horizons on test."
                ),
                "per_super_node": arima_per_node,
            }
        else:
            arima_metrics = {
                "rmse": None,
                "mae": None,
                "r2": None,
                "pearson_r": None,
                "n_samples": 0,
                "note": "statsmodels is missing; ARIMA component could not be fit.",
            }
    else:
        # statsmodels missing and allow_ar_fallback=False: report null per contract
        missing_reasons = []
        if not HAS_STATSMODELS:
            missing_reasons.append("statsmodels is missing (ModuleNotFoundError)")
        if not HAS_TORCH:
            missing_reasons.append("torch is missing")

        arima_metrics = {
            "rmse": None,
            "mae": None,
            "r2": None,
            "pearson_r": None,
            "n_samples": 0,
            "note": (
                f"{'; '.join(missing_reasons)}. Per BAB III contract, ARIMA-LSTM linear component "
                "requires statsmodels; metrics set to null without fabricating numbers."
            ),
        }

    output_payload = {
        "arima_lstm": arima_metrics,
        "xgboost": xgb_metrics,
    }

    # Write output JSON
    out_path = Path(out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    return output_payload


if __name__ == "__main__":
    result = run_baselines()
    print(json.dumps(result, indent=2))
