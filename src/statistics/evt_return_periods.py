"""
evt_return_periods.py — Extreme Value Theory for rainfall & flood depth.

DEPRECATED AS CANONICAL ENTRY POINT (ROZVI Phase 2)
----------------------------------------------------
Prefer ``src.eprf.extremes`` and ``src.eprf.extremes.return_period_report``
for new code.  This module is retained for backward compatibility with the
legacy hydraulics / multi_peril path.

Fits Gumbel or GEV distributions to annual maxima and evaluates quantiles
at industry-standard return periods:

  T ∈ {10, 50, 100, 250, 500} years

Outputs are physical quantities (mm of rain or metres of water), **not**
relative susceptibility scores in [0, 1].
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np
from scipy import stats

from src.utils import get_logger

logger = get_logger(__name__)
logger.debug(
    "src.statistics.evt_return_periods is a compatibility module; "
    "prefer src.eprf.extremes for new development"
)

STANDARD_RETURN_PERIODS: tuple[int, ...] = (10, 50, 100, 250, 500)


def _as_float_array(a: Any) -> np.ndarray:
    return np.asarray(a, dtype="float64")


def annual_maxima_from_daily(
    daily: np.ndarray,
    n_days_per_year: float = 365.25,
) -> np.ndarray:
    """
    Collapse a (time, y, x) daily stack into (n_years, y, x) annual maxima.

    Partial final years are kept if they contain ≥ 180 valid days.
    """
    daily = _as_float_array(daily)
    if daily.ndim != 3:
        raise ValueError(f"daily stack must be (T,Y,X), got {daily.shape}")
    t, y, x = daily.shape
    year_len = int(round(n_days_per_year))
    n_years = t // year_len
    remainder = t - n_years * year_len
    blocks = []
    for i in range(n_years):
        slab = daily[i * year_len : (i + 1) * year_len]
        with np.errstate(all="ignore"):
            am = np.nanmax(slab, axis=0)
        blocks.append(np.where(np.isfinite(am), am, 0.0))
    if remainder >= 180:
        slab = daily[n_years * year_len :]
        with np.errstate(all="ignore"):
            am = np.nanmax(slab, axis=0)
        blocks.append(np.where(np.isfinite(am), am, 0.0))
    if not blocks:
        raise ValueError("Not enough timesteps to form annual maxima.")
    return np.stack(blocks, axis=0)


def fit_gumbel(samples: np.ndarray) -> dict[str, float]:
    """
    Fit Gumbel (Type-I EV) distribution to 1-D finite samples.

    Uses scipy's ``gumbel_r`` (maxima). Returns loc, scale, and n.
    """
    x = _as_float_array(samples).ravel()
    x = x[np.isfinite(x)]
    if x.size < 5:
        raise ValueError(f"Need ≥5 finite samples for Gumbel fit, got {x.size}")
    # Method of moments / MLE via scipy
    loc, scale = stats.gumbel_r.fit(x)
    scale = max(float(scale), 1e-9)
    return {"dist": "gumbel_r", "loc": float(loc), "scale": float(scale), "n": int(x.size)}


def fit_gev(samples: np.ndarray) -> dict[str, float]:
    """
    Fit GEV distribution (shape, loc, scale) to 1-D finite samples.
    """
    x = _as_float_array(samples).ravel()
    x = x[np.isfinite(x)]
    if x.size < 8:
        raise ValueError(f"Need ≥8 finite samples for GEV fit, got {x.size}")
    shape, loc, scale = stats.gev.fit(x)
    scale = max(float(scale), 1e-9)
    return {
        "dist": "gev",
        "shape": float(shape),
        "loc": float(loc),
        "scale": float(scale),
        "n": int(x.size),
    }


def return_level(
    params: dict[str, float],
    return_period_years: float,
) -> float:
    """
    Quantile of the fitted distribution at non-exceedance probability
    p = 1 - 1/T.
    """
    T = float(return_period_years)
    if T <= 1.0:
        raise ValueError("return_period_years must be > 1")
    p = 1.0 - 1.0 / T
    if params["dist"] == "gumbel_r":
        return float(stats.gumbel_r.ppf(p, loc=params["loc"], scale=params["scale"]))
    if params["dist"] == "gev":
        return float(
            stats.gev.ppf(
                p, params["shape"], loc=params["loc"], scale=params["scale"]
            )
        )
    raise ValueError(f"Unknown dist {params['dist']}")


def _fit_pixel_series(
    series: np.ndarray,
    method: str = "gumbel",
) -> Optional[dict[str, float]]:
    x = series[np.isfinite(series)]
    try:
        if method == "gev" and x.size >= 8:
            return fit_gev(x)
        if x.size >= 5:
            return fit_gumbel(x)
    except Exception:
        return None
    return None


def precip_return_period_maps(
    daily_precip: np.ndarray,
    return_periods: Sequence[int] = STANDARD_RETURN_PERIODS,
    method: str = "gumbel",
    n_days_per_year: float = 365.25,
) -> dict[str, Any]:
    """
    Build rainfall intensity maps [mm/day] for each return period.

    Parameters
    ----------
    daily_precip :
        (time, y, x) daily rainfall [mm/day] from CHIRPS/ERA5 streams.
    method :
        ``\"gumbel\"`` (stable for shorter records) or ``\"gev\"``.

    Returns
    -------
    dict
        ``{ \"T10\": 2D array, ..., \"method\": ..., \"n_years\": int }``
    """
    am = annual_maxima_from_daily(daily_precip, n_days_per_year=n_days_per_year)
    n_years, y, x = am.shape
    logger.info(
        "Fitting %s EVT on %d annual maxima maps (%d×%d).",
        method, n_years, y, x,
    )

    out_maps = {f"T{int(T)}": np.full((y, x), np.nan, dtype="float64") for T in return_periods}

    # Vectorized path: fit per-pixel (loop over spatial; series length is small)
    for i in range(y):
        for j in range(x):
            params = _fit_pixel_series(am[:, i, j], method=method)
            if params is None:
                # Fallback: empirical max * simple growth factor
                base = float(np.nanmax(am[:, i, j])) if np.isfinite(am[:, i, j]).any() else 0.0
                for T in return_periods:
                    # Crude EV growth: μ + σ log(T) with σ ≈ 0.3 μ
                    out_maps[f"T{int(T)}"][i, j] = base * (1.0 + 0.3 * np.log(max(T, 2)))
                continue
            for T in return_periods:
                out_maps[f"T{int(T)}"][i, j] = max(return_level(params, T), 0.0)

    out_maps["method"] = method
    out_maps["n_years"] = n_years
    out_maps["unit"] = "mm/day"
    return out_maps


def depth_return_period_from_scenario_depths(
    scenario_depths: dict[int, np.ndarray],
    return_periods: Sequence[int] = STANDARD_RETURN_PERIODS,
) -> dict[str, np.ndarray]:
    """
    Map precomputed design-storm *peak depth* fields onto return periods.

    ``scenario_depths`` keys are return periods (years) and values are 2-D
    max-depth grids [m] from the hydraulic solver forced by the corresponding
    rainfall return level.
    """
    out = {}
    for T in return_periods:
        if int(T) in scenario_depths:
            d = _as_float_array(scenario_depths[int(T)])
            out[f"depth_T{int(T)}_m"] = np.where(np.isfinite(d), np.maximum(d, 0.0), 0.0)
        else:
            logger.warning("No scenario depth for T=%s; skipping.", T)
    return out


def design_storm_hyetograph_mm_h(
    total_depth_mm: float,
    duration_h: float = 24.0,
    peaking_factor: float = 4.0,
    n_steps: int = 24,
) -> np.ndarray:
    """
    Simple Chicago-like design storm [mm/h] from a total event depth.

    Used to drive the SWE solver for a given EVT rainfall return level.
    """
    if duration_h <= 0 or n_steps < 2:
        raise ValueError("Invalid duration/n_steps")
    t = np.linspace(0.0, 1.0, n_steps)
    # Symmetric peak at centre
    w = np.exp(-peaking_factor * (t - 0.5) ** 2)
    w /= w.sum()
    rates = w * total_depth_mm / (duration_h / n_steps)  # mm/h
    return rates.astype("float64")
