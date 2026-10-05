"""Event-based drought verification for SPEI forecasts.

The moderate (SPEI <= -1.0) and severe (SPEI <= -1.5) thresholds mirror
``src/data/spei.classify_spei``. Division by zero in any metric returns
``0.0``. Rows with a non-finite actual or predicted value are excluded.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _safe_divide(numerator: int, denominator: int):
    """Return the ratio, or ``None`` when undefined (denominator == 0).

    ``None`` (undefined) is deliberately distinct from a measured ``0.0`` so a
    metric with no sample is not reported as a real zero score.
    """
    return float(numerator / denominator) if denominator else None


def _event_arrays(actual: Any, predicted: Any) -> tuple[np.ndarray, np.ndarray]:
    actual_array = np.asarray(actual, dtype=float).reshape(-1)
    predicted_array = np.asarray(predicted, dtype=float).reshape(-1)
    if actual_array.size != predicted_array.size:
        raise ValueError("actual and predicted must have the same length")
    valid = np.isfinite(actual_array) & np.isfinite(predicted_array)
    return actual_array[valid], predicted_array[valid]


def contingency(actual: Any, predicted: Any, threshold: float) -> dict[str, Any]:
    """Calculate binary drought contingency counts and verification metrics."""
    actual_array, predicted_array = _event_arrays(actual, predicted)
    observed_drought = actual_array <= threshold
    predicted_drought = predicted_array <= threshold

    hits = int(np.count_nonzero(observed_drought & predicted_drought))
    misses = int(np.count_nonzero(observed_drought & ~predicted_drought))
    false_alarms = int(np.count_nonzero(~observed_drought & predicted_drought))
    correct_negatives = int(np.count_nonzero(~observed_drought & ~predicted_drought))

    return {
        "hits": hits,
        "misses": misses,
        "false_alarms": false_alarms,
        "correct_negatives": correct_negatives,
        "pod": _safe_divide(hits, hits + misses),
        "far": _safe_divide(false_alarms, hits + false_alarms),
        "csi": _safe_divide(hits, hits + false_alarms + misses),
        "f1": _safe_divide(2 * hits, 2 * hits + false_alarms + misses),
        "threshold": threshold,
        "n": int(actual_array.size),
    }


def _threshold_key(threshold: float) -> str:
    return f"<={float(threshold):.1f}"


def evaluate_events(
    df: pd.DataFrame,
    actual_col: str = "actual",
    pred_col: str = "pred_p50",
    thresholds: tuple[float, ...] = (-1.0, -1.5),
) -> dict[str, dict[str, Any]]:
    """Evaluate drought events overall and by available spatial identifier."""
    group_col = next(
        (column for column in ("super_node_id", "city_id") if column in df.columns),
        None,
    )
    results: dict[str, dict[str, Any]] = {}
    for threshold in thresholds:
        result = contingency(df[actual_col], df[pred_col], threshold)
        if group_col is not None:
            result["per_group"] = {
                "group_col": group_col,
                "groups": {
                    str(group): contingency(group_df[actual_col], group_df[pred_col], threshold)
                    for group, group_df in df.groupby(group_col, dropna=False, sort=False)
                },
            }
        results[_threshold_key(threshold)] = result
    return results


if __name__ == "__main__":
    actual = np.array([-1.2, -0.3, -2.0, 0.5])
    predicted = np.array([-1.1, -0.2, -0.5, 0.4])
    result = contingency(actual, predicted, -1.0)
    assert result["hits"] == 1
    assert result["misses"] == 1
    assert result["false_alarms"] == 0
    assert result["correct_negatives"] == 2
    assert result["pod"] == 0.5
    assert result["far"] == 0.0
    assert result["csi"] == 0.5
    assert result["f1"] == 2 / 3
    print(result)
    print("event_metrics self-check: PASS")
