# Re-Audit: TFT-only Robustness Pass (2026-10-05)

Scope: whole repo (`/media/DiskE/SKRIPSI/Skripsi_Nopal`), ponytail-audit + thermonuclear + ponytail-review rubric.
Method: 10 module reviewers (5 × gemini-3.8-flash-high, 5 × gpt-5.6-luna), independent passes, then driver
verification of every BLOCKER by reading the cited `path:line`.
Diff: **14 files, +59 / -736 (net -677 lines)**.

## Model-identity correction (important)

`ROADMAP_TFT_SPEI_HANDOVER.md:25,649` and `:461` state the model is **TFT only** —
"Bukan: graph neural network, RDM, STGNN, GAT". No STGNN/RDM/GNN exists in the repo
(grep = 0 hits). The TFT is the sole model and is retained. The original brief's
"RDM-STGNN" referred to nothing present; all "delete all algorithm except RDM-STGNN"
targets actual non-model code (mocks, duplicate helpers, dead scripts).

## Edits applied (all verified)

| # | Edit | File | Evidence |
|---|------|------|----------|
| 1 | Removed duplicate `haversine_km`; import from `ingest` | `src/data/preprocess.py:9` | grep `^def haversine_km` = 1 hit; numerical parity test `PARITY_OK`; acyclic `preprocess -> ingest -> schema` |
| 2 | Added single-source `SCHEMA_VERSION` | `src/schema.py` (new) | 5 duplicate `= 2` literals collapsed to imports; runtime `SCHEMA_VERSION == 2` |
| 3 | Deleted unmounted mock router | `app/api/v1/endpoints/predict.py` (deleted) | `grep include_router` = 0; file had 0 importers |
| 4 | Deleted non-project image generator | `scripts/agy_image.py` (deleted) | `grep agy_image` = 0 refs |
| 5 | Deleted stale diagnostic script | `_diag2.py` (deleted) | hardcoded removed checkpoint; 0 refs |
| 6 | Removed dead `selection_path` (kept live reassignment) | `app/main.py` | `raw_path` verified still used at `elif raw_path.exists()`; branch smoke = 25 grid items |
| 7 | Fixed `_spei_label` MODERATE boundary `-0.5` -> `-1.0` | `app/main.py:131` | 4-class frontend contract preserved; boundary test all pass |
| 8 | Removed dead `AppState.tft_model` attr + shutdown line | `app/main.py` | grep `tft_model` = only `build_tft_model` |
| 9 | Trimmed 3 uncalled interpretability helpers; **kept** `load_model`,`calculate_metrics` | `src/evaluation/metrics.py` | `test_pipeline.py:104` imports them; math test RMSE/MAE = 1.0 exact |
| 10 | Deleted uncalled `_latest_eval_dir` | `run_experiment.py` | 0 callers |
| 11 | Aligned `CELL_SIZE_KM` 8.0 -> 13.3 (matches ingest spacing) | `scripts/generate_leaflet_final_grid.py:25` | both map scripts now 13.3 = ~0.12 deg lat |
| 12 | Wired real `calculate_spei` (removed dummy `0.1`) | `app/main.py:248-263` | endpoint smoke: deficit 8.0, real series; `None` = canonical insufficient-data |
| 13 | Restored `import warnings` (regression caught in re-audit) | `src/data/preprocess.py:4` | repro `_interpolate_per_node` warns, no NameError |

## Rejected deletions (gpt-luna REFUTED gemini; kept)

- `dataset.py:112` time_idx filter — removing changes training window population → **kept**.
- `dataset.py:12` `ArrayStandardScaler` — serialized in existing checkpoints; removal breaks unpickling → **kept**.
- `tft.py:34` `build_tft_model` — wrapper still earning keep (quantile loss/output_size/defaults) → **kept**.
- `metrics.py` `load_model`/`calculate_metrics` — imported by `test_pipeline.py` → **kept**.
- `run_evaluation.py`, `resume_8var_pipeline.py` — documented CLI entrypoints → **kept**.
- `calibration.py` vectorization — no measured bottleneck, adds risk → **deferred**.

## Verification evidence

- `pytest tests/` → **5 passed**.
- `python test_pipeline.py` → **TEST 1-6 all PASS** (0 FAIL): import, 9 SPEI classes, data integrity,
  31670 sequences, model inference, `evaluate.py` e2e.
- Real TFT metrics: RMSE 0.164, MAE 0.119, R² 0.947, Pearson r 0.974, PICP 0.839 (nominal 0.80),
  beats naive persistence at 29/30 horizons.
- `python -c "import app.main, main, evaluate, full_evaluation, run_experiment, test_pipeline, src.data.preprocess, src.data.ingest, src.schema"` → ALL IMPORTS OK.
- `git diff --stat` → 14 files, +59/-736.

## Honest remaining gaps (NOT fixed)

1. `app/main.py:232-246` `/api/v1/predict` still returns a hardcoded arithmetic array (`-0.5 - i*0.01`)
   labelled `Mild Drought`. Real TFT inference needs encoder-window feature assembly + checkpoint load —
   a design change beyond audit scope. Endpoint advertises TFT but is a stub.
2. `app/main.py:265+` `/api/v1/ingest/status` returns static values; SSE stream emits synthetic weather.
3. `evaluate.py` vs `full_evaluation.py` remain two evaluators with different test windows (duplication, not a
   correctness bug). Consolidation requires a thesis-contract decision.
4. Checkpoints under `logs/` were trained before this pass; no retrain performed (none needed — no model-input
   change was applied).
