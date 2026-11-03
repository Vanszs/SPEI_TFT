# Luaran Jurnal SINTA 4 — TFT + ERA5-Land Bromo

Pipeline kode untuk penelitian *Peramalan Multi-Horizon Suhu Udara Ekstrem di Kawasan
Bromo Tengger Semeru Menggunakan Temporal Fusion Transformer Berbasis ERA5-Land*.

Satu titik grid, satu seri harian, target `t2m_min_c` (suhu minimum harian, proxy
embun upas). TFT dilatih dengan Quantile Loss `[0.1, 0.5, 0.9]`; baseline LSTM
disediakan untuk tabel komparasi.

## Struktur

```
configs/bromo.yaml       konfigurasi titik, split, hyperparameter
main.py                  entry point dari root repo induk
src/acquire_era5.py      unduh ERA5-Land hourly dari Copernicus CDS (validasi + atomic rename)
src/preprocess.py        de-accumulate tp/str, agregasi harian lokal, split kronologis
src/eda.py               seri waktu, siklus musiman, distribusi target
src/dataset.py           TimeSeriesDataSet (encoder 30 hari, decoder 7 hari)
src/models.py            builder TFT, baseline LSTM, loader checkpoint
src/train.py             training Lightning + early stopping + run metadata
src/evaluate.py          MAE/RMSE/SMAPE/PICP + grafik + CSV
src/interpret.py         variable importance + temporal attention TFT
src/compare.py           tabel TFT vs LSTM
src/run_all.py           orkestrasi seluruh tahap
tests/test_core.py       regression checks untuk de-accumulation, gap, metrik
data/                    raw NetCDF dan processed parquet (git-ignored)
logs/                    checkpoint dan run config (git-ignored)
results/                 metrik, CSV prediksi, gambar (git-ignored)
```

## Setup

```bash
cd luaran_jurnal_sinta
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Buat `~/.cdsapirc`:

```yaml
url: https://cds.climate.copernicus.eu/api
key: <personal-access-token>
```

Gunakan `cdsapi>=0.7` (CDS-Beta). Versi lama tidak mengenal key `data_format`
yang dipakai skrip ini.

## Menjalankan

```bash
# seluruh pipeline (unduh 2016-2025, preprocess, EDA, TFT, LSTM, evaluasi, interpretasi)
python -m src.run_all

# atau bertahap
python -m src.acquire_era5 --config configs/bromo.yaml
python -m src.preprocess
python -m src.eda
python -m src.train --model tft
python -m src.evaluate --model tft
python -m src.interpret
python -m src.train --model lstm
python -m src.evaluate --model lstm
python -m src.compare
```

Tanpa GPU: tambahkan `--cpu` (training jauh lebih lambat). Uji cepat:
`python -m src.train --model tft --max-epochs 2 --cpu`.

Jalankan dari dalam folder `luaran_jurnal_sinta/`; ada paket `src` terpisah dari
repo skripsi induk. Dari root repo induk, gunakan entry point yang mengisolasi path:

```bash
python luaran_jurnal_sinta/main.py --skip-baseline
```

## Artefak

```
data/processed/bromo_daily.parquet
data/processed/bromo_daily.meta.json
logs/checkpoints/tft-<run_id>-<epoch>-<val_loss>.ckpt
logs/run_config_tft.json
results/tft/metrics.json
results/tft/metrics_per_horizon.csv
results/tft/predictions.csv
results/tft/actual_vs_pred.png
results/tft/forecast_last_window.png
results/tft/interpretation/encoder_variable_importance.csv
results/comparison.csv
```

`metrics.json` memuat `overall` (MAE, RMSE, bias, SMAPE, PICP80, MPIW, pinball)
dan `per_horizon`. `overall.n` adalah jumlah observasi horizon yang digabung,
bukan jumlah hari independen; `overall.n_origins` adalah jumlah origin forecast.

## Konfigurasi penting

- `study.latitude/longitude` — titik Bromo (`-7.9425, 112.9530`) atau Ngadas (`-7.9830, 112.9110`).
- `data.target` — `t2m_min_c` (default), `t2m_mean_c`, atau `t2m_max_c`; label grafik mengikuti target.
- `model.max_encoder_length` / `max_prediction_length` — default 30/7 hari.
- `data.split` — kronologis 70/15/15, tanpa shuffle.
- `model.patience` — early stopping; `model.lr_patience` — ReduceLROnPlateau.
- `model.rnn_layers` — jumlah layer baseline LSTM (dropout hanya aktif jika >1).

## Metode & batasan yang harus ditulis di naskah

- `tp` dan `str` ERA5-Land adalah **accumulated fields** sejak 00 UTC. Pipeline
  men-de-accumulate menjadi increment per jam sebelum dijumlahkan per hari.
- Agregasi harian memakai waktu lokal `Asia/Jakarta`; hanya hari dengan 24 sampel
  valid yang dipakai. Hari parsial dibuang.
- Target tidak diinterpolasi. Nilai target yang hilang membuang hari tersebut;
  kovariat boleh diinterpolasi maksimal `data.max_gap_fill_days`.
- Suhu minimum adalah minimum dari 24 sampel hourly; frost sub-hourly bisa lebih
  rendah, sehingga proxy ini cenderung warm-biased.
- ERA5-Land adalah rata-rata sel ~9 km, bukan elevasi stasiun; tidak ada koreksi
  lapse-rate.
- Hanya 5 variabel cuaca + kalender; satu seri titik. Generalisasi ke wilayah lain
  perlu validasi ulang.
- Baseline LSTM bersifat univariat + fitur kalender karena `RecurrentNetwork`
  tidak menerima kovariat masa lalu dan tidak mendukung `QuantileLoss`; metrik
  interval hanya dilaporkan TFT.
- Metrik dievaluasi pada window uji yang saling tumpang tindih; laporkan
  `n_origins`, bukan hanya `n`. Interval kepercayaan dan baseline naive
  persistence belum dihitung; LSTM adalah pembanding utama.
- `series_id` statis hanya berisi satu nilai (studi kasus satu titik), sehingga
  tidak menambah informasi spasial.
- MAPE tidak dilaporkan karena target Celsius dapat melewati nol; gunakan SMAPE.

## Reproducibility & tests

`logs/run_config_<model>.json` menyimpan seluruh config, versi torch/lightning/
pytorch-forecasting, hash parquet, dan path checkpoint. Training memakai
`deterministic="warn"`.

```bash
python -m unittest discover -s tests -v
```
