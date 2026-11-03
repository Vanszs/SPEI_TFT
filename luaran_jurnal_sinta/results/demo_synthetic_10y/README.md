# SYNTHETIC DEMO — BUKAN HASIL PENELITIAN

Folder ini berisi artefak **demo sintetis** untuk membuktikan pipeline berjalan
end-to-end. Data bukan ERA5-Land observasi dan **tidak boleh** dipakai sebagai
hasil skripsi/jurnal.

## Cara data dibuat

- 120 file NetCDF bulanan, 2016-01-01 s.d. 2025-12-31, satu titik (`-7.9, 112.9`).
- Suhu: siklus musiman + penurunan musim dingin + noise; target `t2m_min_c`.
- `tp` dan `str` dibangkitkan sebagai accumulated fields 00 UTC, lalu pipeline
  men-de-accumulate-nya.
- 3.652 hari harian; 2 hari parsial dibuang; tidak ada gap target/fitur.
- Split kronologis: 2.556 train / 547 val / 549 test.

## Hasil demo (max 80 epoch, early stopping)

| Model | MAE | RMSE | Bias | SMAPE | PICP80 | Origin | n |
|---|---:|---:|---:|---:|---:|---:|---:|
| TFT | 0.3251 | 0.4214 | +0.0201 | 3.46% | 0.8150 | 543 | 3.801 |
| LSTM | 0.3246 | 0.4159 | +0.0300 | 3.44% | — | 543 | 3.801 |

TFT berhenti di epoch 19/80; LSTM di epoch 44/80. LSTM sedikit lebih baik karena
sinyal sintetis murni musiman + noise, bukan bukti performa pada Bromo.

## Isi

```text
comparison.csv
tft/ metrics.json, metrics_per_horizon.csv, predictions.csv, *.png
tft/interpretation/ encoder_variable_importance.csv, temporal_attention.csv, *.png
lstm/ metrics.json, metrics_per_horizon.csv, predictions.csv, *.png
eda/ timeseries.png, seasonal_cycle.png, distribution.png, target_by_split.csv
data_meta.json
```

Run log lengkap: `/tmp/tft_full/full_run2.log` (tidak di-commit).
