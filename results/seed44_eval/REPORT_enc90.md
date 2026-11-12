# TFT SPEI-3 Evaluation Report ? Encoder 90

**Generated:** 2026-06-02 05:15:01  
**Checkpoint:** `/media/DiskE/SKRIPSI/Skripsi_Nopal/logs/checkpoints/enc90-run20260602_030625-epoch=20-val_loss=0.1867.ckpt`  
**Encoder length:** 90 hari  
**Prediction length:** 30 hari  
**Training time:** 7651s (127.5 min)  
**Train split:** year < 2023  
**Val split:** year == 2023  
**Test split:** year >= 2024  

---

## Overall Metrics (Test Set — 2024) — t+1 (step-0)

| Metric | Model | Naive Persistence | Keterangan |
|--------|-------|-------------------|------------|
| RMSE | **0.2768** | 0.1731 | ? lebih baik |
| MAE  | **0.1634** | 0.0683 | ? lebih baik |
| R2   | **0.9202** | 0.9679 | ? lebih baik |
| Pearson r | **0.9622** | 0.9843 | ? lebih baik |
| Bias | **-0.0284** | -0.0063 | mendekati 0 lebih baik |
| PICP (P10?P90) | **0.7986** | ? | nominal = 0.80 |
| Skill Score | **-60.0%** | 0% | positif = model beats naive |

> **PICP nominal:** P10—P90 interval diharapkan mencakup 80% data aktual.
> **Skill Score:** `(1 - RMSE_model / RMSE_naive) × 100%`

### All-Horizon Aggregate (pooled h=1..30)

| RMSE | MAE | R² | Pearson r | Skill Score |
|------|-----|----|-----------|-------------|
| 0.3635 | 0.2574 | 0.8171 | 0.9179 | -0.5997 |

---

## Per-Location Metrics

| Lokasi | RMSE | MAE | R2 | Pearson r | Bias | PICP |
|--------|------|-----|----|-----------|------|------|
| Bojonegoro | 0.3356 | 0.1790 | 0.8965 | 0.9544 | -0.0717 | 0.8634 |
| Lamongan | 0.1949 | 0.1432 | 0.9401 | 0.9725 | 0.0317 | 0.7596 |
| Nganjuk | 0.3139 | 0.1908 | 0.9195 | 0.9605 | -0.0511 | 0.7596 |
| Ngawi | 0.3182 | 0.1844 | 0.9093 | 0.9581 | -0.0459 | 0.7610 |
| Tuban | 0.1811 | 0.1194 | 0.9114 | 0.9550 | -0.0051 | 0.8492 |

---

## Degradasi Metrik per Horizon (hari ke-1, 5, 10, 15, 20, 25, 30)

| Horizon | RMSE | MAE | Bias | Pearson r |
|---------|------|-----|------|-----------|
|   1 | 0.2768 | 0.1634 | -0.0284 | 0.9622 |
|   5 | 0.3085 | 0.2017 | -0.0479 | 0.9495 |
|  10 | 0.3364 | 0.2366 | -0.0716 | 0.9368 |
|  15 | 0.3703 | 0.2659 | -0.0660 | 0.9151 |
|  20 | 0.3920 | 0.2872 | -0.0471 | 0.8958 |
|  25 | 0.4042 | 0.3024 | -0.0273 | 0.8814 |
|  30 | 0.4085 | 0.3121 | -0.0106 | 0.8716 |

---

## File Output

Semua hasil disimpan di: `/media/DiskE/SKRIPSI/Skripsi_Nopal/results/full_eval_20260602_051347`

| File | Keterangan |
|------|------------|
| `metrics_summary.json` | Semua metrik dalam format JSON |
| `metrics_report.txt` | Laporan teks lengkap |
| `predictions_full.csv` | Tabel prediksi vs aktual |
| `horizon_metrics.csv` | RMSE/MAE/Bias per horizon step |
| `classification_report.csv` | Akurasi per kelas SPEI (9-class) |
| `classification_summary.csv` | Akurasi 3-class per lokasi |
| `01_scatter_overall.png` | Scatter actual vs predicted |
| `03_timeseries_per_location.png` | Time series overlay |
| `06_horizon_metrics.png` | Degradasi metrik per horizon |
| `08_quantile_fan.png` | Fan chart P10/P50/P90 |
| `09_spei_classification.png` | Confusion matrix SPEI class |
| `11_model_vs_naive_picp.png` | Skill vs naive + PICP coverage |

---

## Interpretasi

?? **Model TIDAK beats naive persistence** (RMSE 0.2768 > 0.1731). Perlu investigasi lebih lanjut.
? **R2 = 0.9202** ? model menjelaskan lebih dari 50% variansi.
? **PICP = 0.7986** ? interval P10?P90 terkalibrasi baik (nominal 80%).
