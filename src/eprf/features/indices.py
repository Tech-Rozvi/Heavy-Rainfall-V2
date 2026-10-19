"""
ETCCDI extreme-precipitation indices.

These indices characterise the *historical* rainfall climate.  They are
outputs of the analysis, not predictors of rainfall in a susceptibility
score (to avoid circularity).  They may be used as targets for supervised
models or as diagnostic layers.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

WET_DAY_MM = 1.0


def _safe_nanmax(arr: np.ndarray, axis: int = 0) -> np.ndarray:
    a = np.asarray(arr, dtype="float64")
    filled = np.where(np.isfinite(a), a, -np.inf)
    out = np.max(filled, axis=axis)
    return np.where(np.isfinite(out) & (out > -np.inf / 2), out, np.nan)


def _safe_nanpercentile(arr: np.ndarray, q: float, axis: int = 0) -> np.ndarray:
    with np.errstate(all="ignore"):
        out = np.nanpercentile(arr, q, axis=axis)
    return np.where(np.isfinite(out), out, np.nan)


def _rolling_sum(arr: np.ndarray, window: int, axis: int = 0) -> np.ndarray:
    csum = np.nancumsum(arr, axis=axis)
    # pad
    pad_width = [(0, 0)] * arr.ndim
    pad_width[axis] = (1, 0)
    csum = np.pad(csum, pad_width, mode="constant", constant_values=0)
    slicer_hi = [slice(None)] * csum.ndim
    slicer_lo = [slice(None)] * csum.ndim
    slicer_hi[axis] = slice(window, None)
    slicer_lo[axis] = slice(None, -window)
    return csum[tuple(slicer_hi)] - csum[tuple(slicer_lo)]


def compute_etccdi_indices(
    daily_precip: np.ndarray,
    n_years: Optional[float] = None,
) -> dict[str, np.ndarray]:
    """
    Compute standard ETCCDI indices from a (T, Y, X) daily stack.

    Returns
    -------
    dict of 2-D arrays:
        map_mm, rx1day, rx5day, r95p, r99p, r10mm, r20mm, cdd, cwd
    """
    p = np.asarray(daily_precip, dtype="float64")
    if p.ndim != 3:
        raise ValueError(f"Expected (T,Y,X), got {p.shape}")
    t, y, x = p.shape
    if n_years is None:
        n_years = t / 365.25

    with np.errstate(all="ignore"):
        total = np.nansum(p, axis=0)
        map_mm = total / max(n_years, 1e-6)

        rx1day = _safe_nanmax(p, axis=0)

        # Rx5day
        if t >= 5:
            r5 = _rolling_sum(np.nan_to_num(p, nan=0.0), 5, axis=0)
            rx5day = _safe_nanmax(r5, axis=0)
        else:
            rx5day = rx1day.copy()

        # Percentile-based (wet-day)
        wet = np.where(p >= WET_DAY_MM, p, np.nan)
        p95 = _safe_nanpercentile(wet, 95, axis=0)
        p99 = _safe_nanpercentile(wet, 99, axis=0)
        r95p = np.nansum(np.where(p > p95, p, 0.0), axis=0) / max(n_years, 1e-6)
        r99p = np.nansum(np.where(p > p99, p, 0.0), axis=0) / max(n_years, 1e-6)

        r10mm = np.nansum(p >= 10.0, axis=0) / max(n_years, 1e-6)
        r20mm = np.nansum(p >= 20.0, axis=0) / max(n_years, 1e-6)

        # CDD / CWD (max consecutive)
        dry = (p < WET_DAY_MM) | ~np.isfinite(p)
        wet_b = (p >= WET_DAY_MM) & np.isfinite(p)
        cdd = _max_run(dry)
        cwd = _max_run(wet_b)

    return {
        "map_mm": map_mm,
        "rx1day": rx1day,
        "rx5day": rx5day,
        "r95p": r95p,
        "r99p": r99p,
        "r10mm": r10mm,
        "r20mm": r20mm,
        "cdd": cdd,
        "cwd": cwd,
        "p95_threshold": p95,
        "p99_threshold": p99,
    }


def _max_run(bool_arr: np.ndarray) -> np.ndarray:
    """Maximum consecutive True run along axis 0."""
    a = np.asarray(bool_arr, dtype=bool)
    # cumulative
    t, y, x = a.shape
    max_run = np.zeros((y, x), dtype="float64")
    cur = np.zeros((y, x), dtype="float64")
    for i in range(t):
        cur = np.where(a[i], cur + 1, 0)
        max_run = np.maximum(max_run, cur)
    return max_run
