# BAB III Alignment — Implementation Audit

Reference: `/home/vanszs/Downloads/skripsi nopal.pdf`, **BAB III METODE PENELITIAN** (lines 1682-2550).
BAB IV ignored (stated fake/dummy by author). Main model = **TFT only** (no GNN/STGNN/RDM).

## Status per subbab

| Subbab | Methodology | Code | Status |
|---|---|---|---|
| 3.3 | Open-Meteo Archive, 5 kabupaten, timezone Asia/Jakarta | `src/data/ingest.py` (`BASE_URL`, `timezone`) | MATCH |
| 3.3 | chronological split <2023 / 2023 / >=2024 | `src/training/train.py:164-176` | MATCH |
| 3.4.1 | temporal continuity, key uniqueness | `preprocess._validate_raw_schema`, `ingest` dup checks | MATCH |
| 3.4.2 | forward-fill limit=7 per node, no bfill | `preprocess._interpolate_per_node` (ffill limit=7) | MATCH |
| 3.4.3 | train-only node selection (<=2022-12-31) | `preprocess.preprocess_pipeline` `selection_end_date` | MATCH |
| 3.4.4 | behavior/distance hybrid + **S1-S5 sensitivity** | `_compute_similarity` + **new** `scripts/node_weight_sensitivity.py` | ADDED |
| 3.4.5 | save selection artifact JSON | `selection_metadata_path` | MATCH |
| 3.4.6 | mean aggregation per (city,time) | `preprocess` agg_map mean | MATCH |
| 3.4.7 | water_deficit, Pseudo-SPEI-3, fisk, log, month_sin/cos, time_idx | `spei.calculate_spei`, `preprocess` | MATCH |
| 3.5 | encoder 90 / decoder 30, group=super_node_id only | `dataset.py:7-9,115` | MATCH |
| 3.5 | feature mapping (static cat/real, tv known/unknown) | `dataset.py:120-139` | MATCH |
| 3.6 | `TemporalFusionTransformer.from_dataset` + quantiles | `tft.build_tft_model` | MATCH |
| 3.7.1 | batch32, lr3e-4, hidden48, dropout0.40, heads1, q[.1,.5,.9] | `train.py`, `tft.py` | MATCH |
| 3.7.3 | gradient clip 0.5, Adam, wd 1e-4 | `train.py:106-107,208` | MATCH |
| 3.7.4 | val 2023 + 90d warmup, early-stop patience10, max60 | `train.py:174-176,210-211,98` | MATCH |
| 3.7.5 | calibration 0.80 / floor 0.5 / min 5 / per city / val only | `calibration.py:12,26,32` | MATCH |
| 3.8.1 | **3-model comparison: TFT + ARIMA-LSTM + XGBoost** | **new** `src/evaluation/baselines.py` + `scripts/bab3_evaluation.py` | ADDED |
| 3.8.2 | **POD/FAR/CSI/F1** contingency, thresholds −1.0 / −1.5 | **new** `src/evaluation/event_metrics.py` | ADDED |
| 3.9 | **Vue.js + FastAPI** web | FastAPI yes; frontend = **Vue 3.5 + Vite** | MATCH |

## B. §3.8.1 comparison evidence (real, all horizons, test 2024+, n samples shown)

| Model | RMSE | MAE | R² | Pearson r | n |
|---|---:|---:|---:|---:|---:|
| TFT (all 30 horizons) | 0.438 | 0.314 | 0.734 | 0.880 | 105450 |
| XGBoost (direct 30-h) | 0.400 | 0.294 | 0.677 | 0.828 | 91950 |
| Hybrid ARIMA-LSTM (iter. 30-h) | 0.926 | 0.735 | −0.733 | 0.655 | 91950 |

Note: TFT n=105450 vs baselines n=91950 — TFT windows retain 2023 as encoder warmup (thesis §3.7.4),
baselines start at 2024; matched as closely as the artifacts allow. Unified JSON: `results/bab3_evaluation.json`.
TFT step-0 only metric (RMSE 0.338) kept under `tft.step0` for reference, not used for the fair comparison.
Dependency added: `statsmodels>=0.14.0`, `xgboost>=2.0.0` (requirements.txt).

## A. Dummy removal (fastapi layer)

Old dummy behaviour removed and replaced with real computation:

| Endpoint | Before (dummy) | After (real) |
|---|---|---|
| `POST /api/v1/predict` | `-0.5 - i*0.01`, `"Mild Drought"` | TFT checkpoint inference via `src/evaluation/inference.py`; `_spei_label(median(p50))` |
| `POST /api/v1/spei/calculate` | constant `0.1` | canonical `src.data.spei.calculate_spei` |
| `GET /api/v1/ingest/status` | static `"synced"`/81 | real processed-artifact mtime + real `raw_node_id` count |
| `GET /api/v1/stream/weather` (SSE) | synthetic random weather | latest **real** observations + `classify_spei` label |

Evidence: `tests/test_api.py` 5 passed with real inference; manual E2E returned
`PREDICT 200 dates ['2026-03-03','2026-03-04','2026-03-05'] p50 [0.868,0.860,0.859] NORMAL`,
`INGEST 200 {'synced', '2026-06-01T05:07:31Z', 45}`, `SSE 200 event: weather_update`.

## C. Event metrics evidence (real artifact)

`results/full_eval_20260602_063310/predictions_full.csv` (3515 rows):

| Threshold | Hits | Misses | FA | CN | POD | FAR | CSI | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ≤ −1.0 | 216 | 68 | 51 | 3180 | 0.7606 | 0.1910 | 0.6448 | 0.7840 |
| ≤ −1.5 | 110 | 33 | 45 | 3327 | 0.7692 | 0.2903 | 0.5851 | 0.7383 |

## E. Weight sensitivity evidence (real parquet)

| Scenario | w_b/w_d | stability_total | mean_representativeness |
|---|---|---:|---:|
| S1 | 0.5/0.5 | 24 | 0.9641 |
| S2 | 0.6/0.4 | 24 | 0.9641 |
| S3 | 0.7/0.3 | 25 | 0.9733 |
| S4 | 0.8/0.2 | 25 | 0.9733 |
| S5 | 1.0/0.0 | 25 | 0.9733 |

S3–S5 tie; S3 chosen (distance term retained). Artifact `results/bab3_node_weight_sensitivity.json`.

## F. §3.9 framework — RESOLVED (migrated to Vue 3)

BAB III §3.9 specifies **Vue.js**; the frontend has been migrated from React 19 to **Vue 3.5 + Vite**
to match the text. `vue-tsc -b && vite build` exits 0; bundle shrank 1410 kB → 866 kB; the API
contract (`/api/v1/study/regions`, SSE `/api/v1/stream/weather`, WS `/ws/monitoring`) is unchanged.

Migration evidence:
- Ported to SFC: `App.vue`, `components/{DroughtMap,ExportModal,TFTFanChart}.vue`; hook →
  `composables/useDroughtStream.ts`; `main.tsx` → `main.ts`.
- `recharts` removed; `TFTFanChart` hand-rolls SVG (q10–q90 band, dashed q50, solid historical,
  threshold lines at −2.0/−1.5/−0.5, selected-horizon marker). `lucide-react` → `lucide-vue-next`.
- Kept untouched: `types.ts`, `api.ts`, `data/mockData.ts`, `utils/generateReport.ts` (jsPDF+html2canvas), `index.css`.
- Post-migration review found + fixed: dead `props.onX?.()` no-op calls removed (emit-only), and an
  empty-history `slice(-1)` that would blank the forecast chart → `slice(Math.max(0, lastHistIndex))`.
- Verified: `pnpm run build` exit 0 · grep react/recharts/lucide-react = 0 · `find src -name '*.tsx'` = 0 · dev server serves HTML.

## Thermo-nuclear self-review (adversarial, gemini + gpt-luna)

Found + fixed real regressions in my own pass (each verified by reading the line):

| # | Finding | Fix | Evidence |
|---|---|---|---|
| 1 | **orphaned duplicate `weather_inference_generator`** stub (body `step = 0`) shadowed by a later def — tests passed only by definition order | removed the orphan | `grep -c "^async def weather_inference_generator"` = 1 |
| 2 | **fake ARIMA**: fit statsmodels ARIMA but forecast with `mean(last_diffs)*0.5`, ignoring fitted φ | real AR recursion with fitted `ar.L*` params | ARIMA-LSTM RMSE 0.926→**0.594**, R² −0.733→**0.287** |
| 3 | **forecast was the observed tail**, not future; dates 90 days wrong (`min_time + time_idx`) | anchor = `time - time_idx`; append genuine future rows | dates now `2026-01-02..`, `all strictly future? True` |
| 4 | `historical_spei` faked `predicted := actual` (perfect predictions) | join real `pred_p50` by date, `None` when absent | — |
| 5 | `forecast_days` accepted 1–90 but silently truncated at 30 | bound `le=30` | — |
| 6 | `event_metrics` returned `0.0` for undefined metrics (fake-perfect) | return `None` (distinct from measured 0) | self-check PASS; `full_evaluation` already maps None→NaN |
| 7 | `per_super_node` key even when grouped by city | renamed `per_group` + `group_col` | — |
| 8 | `full_evaluation` local `_event_metrics` duplicated the canonical module | call `src.evaluation.event_metrics.contingency` | — |
| 9 | `_calc_metrics` duplicated `_metrics` with drifted keys | canonical `src/evaluation/point_metrics.point_metrics` | — |
| 10 | `run_experiment` wiped `results/*.json` incl. thesis artifacts | allowlist preserves `bab3_*.json` | — |
| 11 | ingest fabricated `elevation=0.0` when API omits it | raise instead of fabricate | — |
| 12 | `bab3_evaluation` read one hardcoded stale dir silently | `_resolve_tft_artifact()` newest-with-both, fail loud | — |

Final §3.8.1 (all 30 horizons, test 2024+): TFT RMSE 0.438 / R² 0.734 · XGBoost 0.400 / 0.677 · ARIMA-LSTM 0.594 / 0.287.
Re-verified: pytest 5 passed · test_pipeline 0 FAIL (exit 0) · dummy grep CLEAN.

## Exit-code + robustness fixes (ponytail pass)

| # | Defect | Fix | Evidence |
|---|---|---|---|
| A | `main.py` swallowed ingestion/preprocess/training errors and returned 0 | `sys.exit(1)` after printing | bad `--city-config` → `SystemExit 1` |
| B | `test_pipeline.py` printed `[FAIL]` then always exited 0 | `FAILURES` accumulator + `_fail()`/`record_failure()`; `sys.exit(1)` if any | `python test_pipeline.py; echo $?` → **0** clean; forced-FAIL → **1** |
| C | `scripts/run_full_pipeline.py` `--allow-cpu` parsed but never forwarded to training | removed flag + stale usage line | `grep -c allow.cpu` = 0 |
| D | `preprocess` unmeasured `behavior_score` fell back to `-1.0` (fake score) | `np.nan` + explicit drop-with-warning in `_select_top_k_nodes` | edge case drops `n0`; real data has 0 NaN → **selection unchanged (25 nodes)** |

## Not changed (risk-avoiding)

- Existing checkpoints were not retrained; no model-input behaviour was altered (D confirmed parity).
- `dataset.py` tail filter and `ArrayStandardScaler` retained (checkpoint compatibility).
- `--allow-cpu` in `run_experiment.py` did not exist; the dead one was only in `run_full_pipeline.py`.
