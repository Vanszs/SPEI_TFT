# Rencana perbaikan inkonsistensi (audit 10 subagent, terverifikasi)

Repo: `/media/DiskE/SKRIPSI/Skripsi_Nopal`. Gaya ponytail: diff terpendek yang benar, reuse helper kanonik,
hapus sebelum menambah, tanpa abstraksi baru, tanpa angka fabrikasi. Satu penyebab = satu perbaikan di
lapisan kanonik.

**JANGAN** sentuh hyperparameter TFT (enc90/dec30/hidden48/dropout0.40/heads1/q[.1,.5,.9]) dan **JANGAN retrain**.

## P1 — mengubah angka laporan (kerjakan duluan)

1. **Cutoff train ganda.** `src/models/dataset.py:112` memotong 30 hari lagi, padahal
   `src/training/train.py:172` sudah memotong di 2022-12-31 → Desember 2022 hilang dari training.
   Satukan kepemilikan cutoff: `create_dataset` tidak memotong waktu lagi.
   *Bukti:* time_idx max baris train yang benar-benar masuk dataset, sebelum vs sesudah.

2. **Warmup 90 hari tidak ada di `evaluate.py`.** `evaluate.py:155` memakai baris test saja;
   `full_evaluation.py:193 _with_warmup` menambah histori → n=3065 vs n=3515.
   Pakai satu jalur warmup kanonik di `evaluate.py`.
   *Bukti:* n + RMSE sebelum vs sesudah; n harus menyamai `full_evaluation`.

3. **Kalibrasi tidak diterapkan di jalur inferensi.** `full_evaluation.py:443` memakai faktor
   `src/evaluation/calibration.py`; `src/evaluation/inference.py` tidak (0 kemunculan) → band web mentah.
   Terapkan faktor yang sama di inferensi (simpan/baca faktor) ATAU tandai eksplisit beda kontrak.
   Jangan fabrikasi faktor.
   *Bukti:* P10/P90 satu kota sebelum vs sesudah.

## P2 — salah tampilan

4. **Dua model untuk satu app.** `app/main.py:145` hardcode `results/full_eval_20260602_063310`
   (ckpt val_loss 0.2405); `/api/v1/predict` memakai `logs/run_config.json` (0.1867).
   Satukan resolver: satu checkpoint untuk semua endpoint.
   *Bukti:* cetak checkpoint tiap endpoint setelah perubahan → identik.

5. **Label risiko beda kontrak.** `app/main.py:283` `_spei_label` (4 kelas Inggris);
   `app/main.py:386` `classify_spei` (9 kelas Indonesia), SPEI sama.
   Pakai satu adapter kontrak respons.
   *Bukti:* SPEI sama → label sama dari kedua endpoint.

6. **Cakupan metrik kejadian beda.** `scripts/bab3_evaluation.py:59` step-0 (n=3515);
   `full_evaluation.py:459` all-horizon (n=105450). Pilih satu cakupan, tulis eksplisit `scope` + `n` di JSON.
   *Bukti:* JSON memuat scope + n yang cocok.

7. **`historical_spei` predicted selalu null.** `app/main.py:238`; rentang tanggal tak beririsan.
   Sejajarkan jendela histori dengan rentang prediksi yang tersedia.
   *Bukti:* endpoint mengembalikan `predicted` non-null.

## P3 — kebersihan

8. **Docstring vs kode.** `src/evaluation/event_metrics.py:5` bilang bagi-nol → `0.0`; kode `:22` → `None`.
   Samakan docstring (None dipertahankan).
9. **Bocor validasi di harness.** `test_pipeline.py:372` pakai `year < 2024`; kanonik `< 2023`.

## Potongan ponytail (bila menyentuh file yang sama)

- hapus `src/evaluation/metrics.py` (29 L; index P50 hardcoded idx 1; hanya dipakai test import) + bereskan import `test_pipeline.py`.
- hapus `run_evaluation.py` (57 L; pembungkus `evaluate.py`).
- hapus `_run()` + `import subprocess` di `run_experiment.py` (evaluasi sudah in-process).
- hapus print "MD report" duplikat `run_experiment.py:391/393`.
- hapus `_raw_has_required_coverage` (`main.py:46`) — duplikat `src/data/ingest.py:189`.

## Bukti wajib

- `python -m pytest tests/ -q` → semua lolos (laporkan jujur bila merah).
- `python test_pipeline.py; echo $?` → exit 0.
- Skrip evaluasi BAB III jalan; JSON memuat `scope` + `n`.
- Item 1–3: angka sebelum vs sesudah (n baris train, n test, P10/P90 satu kota).

## Stop rule

- Perbaikan yang menuntut retrain / mengubah bobot → **JANGAN**; laporkan `blocked`.
- Angka skripsi berubah → jangan tulis ulang dokumen skripsi; laporkan lama vs baru.
- Dua pilihan sama benar → ambil diff terpendek.
- Klaim tanpa bukti eksekusi → jangan sebut "beres".

## Scope

`src/`, `app/`, `scripts/`, `tests/`, `evaluate.py`, `full_evaluation.py`, `run_experiment.py`,
`main.py`, `test_pipeline.py`. **JANGAN** sentuh `data/raw`, `data/processed`, `venv/`,
`node_modules/`, `frontend/dist`, checkpoints, atau berkas .md skripsi.