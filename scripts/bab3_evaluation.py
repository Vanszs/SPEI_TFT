"""BAB III combined evaluation runner.

Produces one JSON with the thesis §3.8 comparison:
- TFT (from the evaluation artifact)           §3.8.1
- Hybrid ARIMA-LSTM baseline                   §3.8.1
- XGBoost baseline                             §3.8.1
- Event metrics POD/FAR/CSI/F1 for the TFT     §3.8.2 (thresholds -1.0, -1.5)

Run: python -m scripts.bab3_evaluation
"""
import json
from pathlib import Path

import pandas as pd

from src.evaluation.baselines import run_baselines
from src.evaluation.event_metrics import evaluate_events

RESULTS_DIR = Path("results")
OUT_PATH = RESULTS_DIR / "bab3_evaluation.json"


def _resolve_tft_artifact() -> tuple[Path, Path]:
    """Pick the newest TFT eval directory that has both required artifacts.

    Fails loudly rather than silently mixing runs or emitting a partial result.
    """
    candidates = sorted(RESULTS_DIR.glob("full_eval_*"), reverse=True)
    for d in candidates:
        summary, preds = d / "metrics_summary.json", d / "predictions_full.csv"
        if summary.exists() and preds.exists():
            return summary, preds
    raise FileNotFoundError(
        "No full_eval_* directory with both metrics_summary.json and "
        "predictions_full.csv under results/. Run full_evaluation.py first."
    )


def tft_metrics_and_events() -> tuple[dict, dict]:
    TFT_SUMMARY_PATH, TFT_PRED_PATH = _resolve_tft_artifact()
    summary = json.loads(TFT_SUMMARY_PATH.read_text(encoding="utf-8"))

    # §3.8.1 fair point comparison = all-horizon (t+1..t+30), matching the baselines.
    all_h = dict(summary.get("overall_all_horizons", {}))
    all_h["metric"] = "all_horizons (t+1..t+30)"
    all_h["skill_score"] = summary.get("skill_score_all_horizons")
    all_h["n_samples"] = all_h.pop("n", None)
    all_h["note"] = (
        "TFT P50 point forecast aggregated over all 30 horizons (fair §3.8.1 comparison). "
        f"Artifact {TFT_SUMMARY_PATH}."
    )

    step0 = dict(summary.get("overall", {}))
    step0["metric"] = "step0 (t+1 only)"

    # Dua cakupan HARUS dibedakan eksplisit: step-0 (n kecil, dari predictions_full.csv)
    # vs all-horizon (n besar, dari metrics_summary.json). Sebelumnya JSON hanya memuat
    # step-0 tanpa label sehingga bisa disalahartikan sebagai angka all-horizon.
    events = {
        "scope_note": (
            "step0 = t+1 saja (prediksi baris pertama tiap window); "
            "all_horizons = t+1..t+30 di-pool. Jangan bandingkan keduanya."
        ),
        "step0": {"note": "no TFT predictions to verify"},
        "all_horizons": summary.get("event_detection", {"note": "not present in metrics_summary.json"}),
    }
    if TFT_PRED_PATH.exists():
        df = pd.read_csv(TFT_PRED_PATH)
        step0_events = evaluate_events(df, actual_col="actual", pred_col="pred_p50", thresholds=(-1.0, -1.5))
        step0_events["scope"] = "step0"
        step0_events["n_samples"] = int(len(df))
        events["step0"] = step0_events
    return {"all_horizons": all_h, "step0": step0}, events


def main():
    print("Running BAB III evaluation...")
    tft, tft_events = tft_metrics_and_events()
    print("  TFT metrics done")
    baselines = run_baselines()
    print("  baselines done")

    payload = {
        "reference": "BAB III (Metode Penelitian): 3.8.1 comparison, 3.8.2 event verification",
        "thresholds": {"moderate_drought": -1.0, "severe_drought": -1.5},
        "tft": tft,
        "tft_event_metrics": tft_events,
        "arima_lstm": baselines["arima_lstm"],
        "xgboost": baselines["xgboost"],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved: {OUT_PATH}")

    print("\n=== §3.8.1 point metrics (test, all 30 horizons) ===")
    for name in ("tft", "arima_lstm", "xgboost"):
        m = payload[name]
        if name == "tft":
            m = m["all_horizons"]
        print(f"{name:11} RMSE={m.get('rmse')} MAE={m.get('mae')} R2={m.get('r2')} r={m.get('pearson_r')} n={m.get('n_samples')}")
    print("\n=== §3.8.2 TFT event metrics (scope diberi label) ===")
    ev = payload["tft_event_metrics"]
    for k, v in ev.get("step0", {}).items():
        if isinstance(v, dict) and v.get("pod") is not None:
            print(f"step0        {k}: POD={v['pod']:.3f} FAR={v['far']:.3f} CSI={v['csi']:.3f} F1={v['f1']:.3f} n={v.get('n')}")
    allh = ev.get("all_horizons", {})
    for name, block in allh.items():
        if isinstance(block, dict) and isinstance(block.get("overall_all_horizons"), dict):
            v = block["overall_all_horizons"]
            print(f"all_horizons {name}: POD={v['pod']:.3f} FAR={v['far']:.3f} CSI={v['csi']:.3f} F1={v['f1']}")


if __name__ == "__main__":
    main()
