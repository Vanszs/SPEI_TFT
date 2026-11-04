import warnings

import numpy as np
import pandas as pd
from scipy.stats import fisk, norm


def calculate_water_deficit(df):
    """
    D = P - PET (Water Deficit)
    ET0 (FAO Penman-Monteith) is used as PET proxy.
    Sesuai Vicente-Serrano et al. (2010)
    """
    return df["precipitation_sum"] - df["et0_fao_evapotranspiration"]


EPS_P = 1e-6
# Satu sumber kebenaran untuk ambang kelas (dipakai API, artefak, dan evaluasi).
SEVERITY_THRESHOLDS = {"moderate": -1.0, "severe": -1.5, "extreme": -2.0, "light": -0.5}
Z_FLOOR = float(norm.ppf(EPS_P))


def _fit_fisk(values):
    """Fit one log-logistic to `values`, returning (c, scale, shift, x_eps) or None."""
    valid = values[np.isfinite(values)]
    if len(valid) < 10:
        return None
    shift = 0.0
    if valid.min() <= 0:
        shift = abs(valid.min()) + 1.0
    try:
        c, _loc, dist_scale = fisk.fit(valid + shift, floc=0)
    except (RuntimeError, ValueError, FloatingPointError) as exc:
        warnings.warn(f"SPEI fitting failed: {exc}. Leaving as NaN.")
        return None
    dist_scale = float(dist_scale) if dist_scale > 0 else 1.0
    x_eps = float(fisk.ppf(EPS_P, c, 0.0, dist_scale))
    return float(c), dist_scale, float(shift), x_eps


def _fit_month_params(d_accumulated, months, fit_mask):
    """One log-logistic per calendar month, fitted on the training period only."""
    params = {}
    for month in range(1, 13):
        mask = months == month
        subset = d_accumulated[fit_mask & mask] if fit_mask is not None else d_accumulated[mask]
        fitted = _fit_fisk(np.asarray(subset, dtype=float))
        if fitted is not None:
            params[month] = fitted
    return params


def calculate_spei(series, scale=3, fit_mask=None):
    """
    Daily SPEI for a given time scale (e.g., 3 months), using a log-logistic
    (fisk) distribution per Vicente-Serrano et al. (2010).

    ET0 (FAO Penman-Monteith) is used as PET proxy in the water deficit input.
    Input is daily data; scale (months) is converted to ~30 days/month.

    Continuity (fix): fitting one distribution per calendar month and applying
    each month's parameters to its own days makes the index jump at every month
    boundary (~1 sigma on average, up to 4.4 sigma), because the fitted location
    and support change discontinuously while the 90-day water balance does not.
    Parameters are therefore interpolated linearly between adjacent month centres
    (the 15th), which is continuous in time while keeping the seasonal
    standardisation. Without this the target is a sawtooth and the model learns
    the sawtooth instead of the climate signal.

    Parameters
    ----------
    fit_mask : pd.Series or None
        Boolean Series aligned to series.index. True = train period rows used
        for fitting distribution parameters. When None, fit on all data (legacy).
    """
    window_days = scale * 30
    d_accumulated = series.rolling(window=window_days, min_periods=window_days).sum()

    index = pd.DatetimeIndex(series.index)
    months = index.month.values

    params = _fit_month_params(d_accumulated, months, fit_mask)
    fallback = _fit_fisk(np.asarray(
        d_accumulated[fit_mask] if fit_mask is not None else d_accumulated, dtype=float
    ))
    if not params and fallback is None:
        return pd.Series(np.nan, index=series.index, dtype=float)
    for month in range(1, 13):
        params.setdefault(month, fallback or next(iter(params.values())))

    centres = pd.Series(
        [pd.Timestamp(t.year, t.month, 15) for t in index], index=index
    )
    after_mid = pd.Series(index.day >= 15, index=index)
    prev_centre = centres.where(after_mid, centres - pd.DateOffset(months=1))
    next_centre = prev_centre + pd.DateOffset(months=1)
    span = (next_centre - prev_centre).dt.days.replace(0, 1)
    weight = ((index - prev_centre).dt.days / span).to_numpy(dtype=float)

    def _lerp(position):
        table = np.array([params[m][position] for m in range(1, 13)])
        return table[prev_centre.dt.month.to_numpy() - 1] * (1 - weight) + \
               table[next_centre.dt.month.to_numpy() - 1] * weight

    shape = _lerp(0)
    dist_scale = _lerp(1)
    shift = _lerp(2)
    x_eps = _lerp(3)

    x = d_accumulated.to_numpy(dtype=float) + shift
    cdf = np.clip(fisk.cdf(x, shape, 0.0, dist_scale), EPS_P, 1 - EPS_P)
    z = norm.ppf(cdf)

    # Values below the fitted support (unprecedented droughts) stay distinct and
    # ordered: extrapolate z linearly below x_eps instead of collapsing to one value.
    below = x <= x_eps
    if np.any(below):
        z[below] = Z_FLOOR + (x[below] - x_eps[below]) / dist_scale[below]
    z[~np.isfinite(x)] = np.nan

    spei_values = pd.Series(z, index=series.index, dtype=float)
    spei_values.replace([np.inf, -np.inf], np.nan, inplace=True)
    return spei_values


def classify_spei(value):
    """
    Standardized SPEI classification (McKee et al., 1993 / WMO).
    Consistent thresholds used across all scripts.
    """
    if value <= SEVERITY_THRESHOLDS["extreme"]: return "Kekeringan Ekstrem"
    elif value <= SEVERITY_THRESHOLDS["severe"]: return "Kekeringan Parah"
    elif value <= SEVERITY_THRESHOLDS["moderate"]: return "Kekeringan Sedang"
    elif value < SEVERITY_THRESHOLDS["light"]: return "Kekeringan Ringan"
    elif value <= 0.5: return "Normal"
    elif value < 1.0: return "Basah Ringan"
    elif value < 1.5: return "Basah Sedang"
    elif value < 2.0: return "Basah Parah"
    else: return "Basah Ekstrem"
