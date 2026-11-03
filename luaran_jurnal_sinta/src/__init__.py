"""Pipeline kode luaran jurnal SINTA 4: TFT + ERA5-Land Bromo."""

import warnings

# Hanya warning kosmetik dari sklearn saat plot_interpretation mem-passing ndarray
# ke scaler yang di-fit pada DataFrame. Jangan menyembunyikan warning pengguna lain.
warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names, but StandardScaler was fitted with feature names",
    category=UserWarning,
    module="sklearn",
)
