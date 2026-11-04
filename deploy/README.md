# Penjadwalan pembaruan data

Model TIDAK dilatih ulang. Yang diperbarui: data mentah (delta Open-Meteo),
parquet, lalu prakiraan 30 hari + riwayat 3 jendela.

# Penjadwalan pembaruan data

## Cara utama: PM2 (ikut deployment web)

`ecosystem.config.js` punya app ketiga:

```
tft-data-scheduler  ->  python3 -u -m scripts.scheduler
```

```bash
pm2 start ecosystem.config.js --only tft-data-scheduler
pm2 save
```

Proses ini tidur sampai tanggal 1 pukul 05:15, menjalankan
`scripts.update_weekly`, lalu tidur lagi. `instances: 1` + file lock
(`logs/update_weekly.lock`) mencegah dua pembaruan berjalan bersamaan.

Sengaja bukan di dalam FastAPI: uvicorn berjalan dengan `--workers 2`,
sehingga penjadwal in-process akan berjalan dua kali.


## Opsi cadangan — cron (jika PM2 tidak dipakai)

```bash
crontab -e
# tambahkan:
15 5 1 * * cd /media/DiskE/SKRIPSI/Skripsi_Nopal && /home/vanszs/.pyenv/shims/python3 -m scripts.update_weekly >> logs/update-weekly.log 2>&1 # nusapantau-monthly-update
```

## Opsi B — systemd user timer

```bash
mkdir -p ~/.config/systemd/user
cp deploy/nusapantau-update.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now nusapantau-update.timer
loginctl enable-linger "$USER"   # agar tetap jalan saat logout
systemctl --user list-timers | grep nusapantau
```

## Manual

```bash
python3 -m scripts.update_weekly          # delta -> preprocess -> forecast + history
python3 -m scripts.forecast_history       # history saja
```

Project ini memakai lag 1 bulan: pada tanggal 1, cutoff = akhir bulan sebelumnya.
Contoh: 4 Nov -> anchor 1 Okt -> cutoff 30 Sep -> prakiraan 1-30 Okt.
