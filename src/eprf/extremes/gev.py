"""
GEV / Gumbel extreme-value modelling for precipitation annual maxima.

Scientific rationale
--------------------
Block-maxima (annual maximum series) is the classical approach for design
rainfall (Coles 2001; WMO guidelines).  We fit the Generalized Extreme Value
distribution by maximum likelihood (scipy.stats.genextreme) and obtain return
levels with parametric bootstrap confidence intervals.

Assumptions (explicitly stated):
- Annual maxima are approximately independent and identically distributed
  (or the non-stationarity is handled externally via climate scaling).
- The block length (1 year) is long enough for the asymptotic GEV to be a
  reasonable approximation.
- Spatial dependence between neighbouring pixels is ignored for the
  per-pixel fit (conservative for uncertainty quantification; spatial
  extremes methods are documented as future work).

Return period T corresponds to the quantile with exceedance probability 1/T
under the fitted distribution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from scipy import stats

from src.utils import get_logger

logger = get_logger(__name__)

STANDARD_RETURN_PERIODS: tuple[int, ...] = (2, 5, 10, 20, 25, 50, 100, 200, 500)


@dataclass
class GEVFit:
    """Container for a single-pixel or scalar GEV fit."""
    shape: float          # xi  (c = -xi in scipy convention)
    loc: float            # mu
    scale: float          # sigma > 0
    n_years: int
    method: str = "MLE"
    converged: bool = True
    aic: Optional[float] = None
    bic: Optional[float] = None


def annual_maxima_series(
    daily: np.ndarray,
    n_days_per_year: float = 365.25,
    min_valid_frac: float = 0.5,
) -> np.ndarray:
    """
    Convert (T, Y, X) daily precipitation to (n_years, Y, X) annual maxima.

    Partial years with fewer than min_valid_frac of days valid are discarded.
    """
    daily = np.asarray(daily, dtype="float64")
    if daily.ndim != 3:
        raise ValueError(f"Expected (T,Y,X), got shape {daily.shape}")
    t, y, x = daily.shape
    year_len = int(round(n_days_per_year))
    n_full = t // year_len
    blocks = []
    for i in range(n_full):
        slab = daily[i * year_len : (i + 1) * year_len]
        valid_frac = np.isfinite(slab).mean(axis=0)
        with np.errstate(all="ignore"):
            am = np.nanmax(slab, axis=0)
        am = np.where(valid_frac >= min_valid_frac, am, np.nan)
        blocks.append(am)
    if not blocks:
        raise ValueError("Insufficient timesteps to form annual maxima.")
    return np.stack(blocks, axis=0)


def _fit_gev_1d(series: np.ndarray) -> GEVFit:
    """MLE fit of GEV to a 1-D annual-maxima series (NaNs dropped)."""
    x = series[np.isfinite(series)]
    n = len(x)
    if n < 10:
        # Fall back to Gumbel (shape=0) with method of moments if too short
        if n < 5:
            return GEVFit(shape=0.0, loc=np.nan, scale=np.nan, n_years=n, converged=False)
        # Gumbel MOM
        mean = float(np.mean(x))
        std = float(np.std(x, ddof=1))
        scale = std * np.sqrt(6) / np.pi
        loc = mean - 0.57721 * scale
        return GEVFit(shape=0.0, loc=loc, scale=max(scale, 1e-6), n_years=n, method="Gumbel-MOM")

    try:
        # scipy.stats.genextreme uses c = -xi
        c, loc, scale = stats.genextreme.fit(x)
        shape = -c
        # Basic convergence / positivity checks
        if scale <= 0 or not np.isfinite([shape, loc, scale]).all():
            raise RuntimeError("Invalid GEV parameters")
        # Information criteria
        loglik = np.sum(stats.genextreme.logpdf(x, c, loc=loc, scale=scale))
        k = 3
        aic = 2 * k - 2 * loglik
        bic = k * np.log(n) - 2 * loglik
        return GEVFit(shape=float(shape), loc=float(loc), scale=float(scale),
                      n_years=n, aic=float(aic), bic=float(bic))
    except Exception as exc:
        logger.debug("GEV MLE failed (%s); falling back to Gumbel MOM", exc)
        mean = float(np.mean(x))
        std = float(np.std(x, ddof=1)) if n > 1 else 1.0
        scale = max(std * np.sqrt(6) / np.pi, 1e-6)
        loc = mean - 0.57721 * scale
        return GEVFit(shape=0.0, loc=loc, scale=scale, n_years=n, method="Gumbel-MOM", converged=False)


def fit_gev_annual_maxima(
    annual_max: np.ndarray,
) -> dict[str, np.ndarray]:
    """
    Fit GEV independently at every pixel.

    Parameters
    ----------
    annual_max : ndarray, shape (n_years, Y, X)

    Returns
    -------
    dict with keys 'shape', 'loc', 'scale', 'n_years', 'converged'
    each of shape (Y, X)
    """
    am = np.asarray(annual_max, dtype="float64")
    if am.ndim != 3:
        raise ValueError("annual_max must be (n_years, Y, X)")
    n_years, ny, nx = am.shape
    shape = np.full((ny, nx), np.nan)
    loc = np.full((ny, nx), np.nan)
    scale = np.full((ny, nx), np.nan)
    n_eff = np.zeros((ny, nx), dtype=int)
    conv = np.zeros((ny, nx), dtype=bool)

    for i in range(ny):
        for j in range(nx):
            fit = _fit_gev_1d(am[:, i, j])
            shape[i, j] = fit.shape
            loc[i, j] = fit.loc
            scale[i, j] = fit.scale
            n_eff[i, j] = fit.n_years
            conv[i, j] = fit.converged

    return {
        "shape": shape,
        "loc": loc,
        "scale": scale,
        "n_years": n_eff,
        "converged": conv,
    }


def _return_level(shape: float, loc: float, scale: float, T: float) -> float:
    """GEV return level for return period T (years)."""
    if not np.isfinite([shape, loc, scale]).all() or scale <= 0:
        return np.nan
    p = 1.0 - 1.0 / T
    # scipy genextreme: c = -shape
    c = -shape
    try:
        return float(stats.genextreme.ppf(p, c, loc=loc, scale=scale))
    except Exception:
        return np.nan


def return_levels_with_ci(
    annual_max: np.ndarray,
    return_periods: Sequence[int] = STANDARD_RETURN_PERIODS,
    n_bootstrap: int = 200,
    ci: float = 0.90,
    random_seed: int = 42,
) -> dict[str, np.ndarray]:
    """
    Compute return levels and bootstrap confidence intervals for every pixel.

    Returns
    -------
    dict
        'rl_{T}'           : central return level (mm)
        'rl_{T}_lower'     : lower CI
        'rl_{T}_upper'     : upper CI
        'shape', 'loc', 'scale', 'n_years', 'converged'
    """
    am = np.asarray(annual_max, dtype="float64")
    if am.ndim != 3:
        raise ValueError("annual_max must be (n_years, Y, X)")
    n_years, ny, nx = am.shape
    rng = np.random.default_rng(random_seed)

    # Point estimates
    params = fit_gev_annual_maxima(am)
    out = {k: v for k, v in params.items()}

    for T in return_periods:
        rl = np.full((ny, nx), np.nan)
        lo = np.full((ny, nx), np.nan)
        hi = np.full((ny, nx), np.nan)
        for i in range(ny):
            for j in range(nx):
                series = am[:, i, j]
                series = series[np.isfinite(series)]
                if len(series) < 8:
                    continue
                # Point estimate
                fit = _fit_gev_1d(series)
                rl[i, j] = _return_level(fit.shape, fit.loc, fit.scale, T)
                # Parametric bootstrap
                boot_vals = []
                for _ in range(n_bootstrap):
                    # Resample from fitted GEV
                    c = -fit.shape
                    try:
                        sample = stats.genextreme.rvs(c, loc=fit.loc, scale=fit.scale,
                                                      size=len(series), random_state=rng)
                        bfit = _fit_gev_1d(sample)
                        boot_vals.append(_return_level(bfit.shape, bfit.loc, bfit.scale, T))
                    except Exception:
                        continue
                if len(boot_vals) >= 20:
                    alpha = (1.0 - ci) / 2.0
                    lo[i, j] = np.nanpercentile(boot_vals, 100 * alpha)
                    hi[i, j] = np.nanpercentile(boot_vals, 100 * (1 - alpha))
        out[f"rl_{T}"] = rl
        out[f"rl_{T}_lower"] = lo
        out[f"rl_{T}_upper"] = hi

    return out
