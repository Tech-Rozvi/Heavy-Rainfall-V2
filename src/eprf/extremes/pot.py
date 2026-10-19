"""
Peaks-over-Threshold (POT) with Generalized Pareto Distribution.

Scientific rationale
--------------------
POT uses more data than annual maxima and is preferred when the threshold
can be chosen so that exceedances are approximately independent and the
GPD approximation holds (Coles 2001; Davison & Smith 1990).  Declustering
is applied with a simple run-length criterion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import stats

from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class GPDFit:
    shape: float
    scale: float
    threshold: float
    n_exceedances: int
    rate: float          # mean exceedances per year
    converged: bool = True


def _decluster(exceed_idx: np.ndarray, min_separation: int = 3) -> np.ndarray:
    """Keep only the maximum of runs separated by < min_separation days."""
    if len(exceed_idx) == 0:
        return exceed_idx
    keep = [exceed_idx[0]]
    for idx in exceed_idx[1:]:
        if idx - keep[-1] >= min_separation:
            keep.append(idx)
    return np.asarray(keep, dtype=int)


def fit_gpd_peaks_over_threshold(
    daily_series: np.ndarray,
    threshold: Optional[float] = None,
    threshold_quantile: float = 0.95,
    min_separation_days: int = 3,
    n_years: Optional[float] = None,
) -> GPDFit:
    """
    Fit GPD to declustered exceedances of a 1-D daily series.

    Parameters
    ----------
    daily_series : 1-D array (days,)
    threshold : absolute threshold (mm). If None, use empirical quantile.
    threshold_quantile : used when threshold is None (default 0.95).
    min_separation_days : declustering gap.
    n_years : length of record in years (for rate calculation).
    """
    x = np.asarray(daily_series, dtype="float64")
    x = x[np.isfinite(x)]
    if len(x) < 50:
        return GPDFit(shape=np.nan, scale=np.nan, threshold=np.nan,
                      n_exceedances=0, rate=0.0, converged=False)

    if threshold is None:
        threshold = float(np.quantile(x[x > 0], threshold_quantile)) if (x > 0).any() else float(np.quantile(x, threshold_quantile))

    exceed_mask = x > threshold
    exceed_idx = np.where(exceed_mask)[0]
    exceed_idx = _decluster(exceed_idx, min_separation_days)
    excesses = x[exceed_idx] - threshold

    if len(excesses) < 15:
        return GPDFit(shape=np.nan, scale=np.nan, threshold=threshold,
                      n_exceedances=len(excesses), rate=0.0, converged=False)

    try:
        # scipy.stats.genpareto: c = shape
        c, _, scale = stats.genpareto.fit(excesses, floc=0)
        shape = float(c)
        scale = float(scale)
        if scale <= 0 or not np.isfinite([shape, scale]).all():
            raise RuntimeError("Invalid GPD parameters")
        if n_years is None:
            n_years = len(x) / 365.25
        rate = len(excesses) / max(n_years, 1e-6)
        return GPDFit(shape=shape, scale=scale, threshold=threshold,
                      n_exceedances=len(excesses), rate=rate)
    except Exception as exc:
        logger.debug("GPD fit failed: %s", exc)
        return GPDFit(shape=np.nan, scale=np.nan, threshold=threshold,
                      n_exceedances=len(excesses), rate=0.0, converged=False)


def gpd_return_level(fit: GPDFit, T: float) -> float:
    """Return level for return period T (years) from a GPD fit."""
    if not fit.converged or fit.rate <= 0 or not np.isfinite(fit.shape):
        return np.nan
    # m-observation return level; here m = T * rate
    p = 1.0 / (T * fit.rate)
    if fit.shape == 0:
        return fit.threshold + fit.scale * (-np.log(p))
    try:
        return fit.threshold + (fit.scale / fit.shape) * (p ** (-fit.shape) - 1)
    except Exception:
        return np.nan
