"""
Rich return-period reporting with mandatory uncertainty and extrapolation flags.

Scientific principle
--------------------
A 500-year return level fitted to a 30-year record is an *extrapolation*.
The system must never present it with the same confidence language as a
10-year level.  Every return-period result carries:

- estimate
- confidence interval
- effective record length
- extrapolation ratio (T / n_years)
- confidence class derived from measurable criteria
- explicit statement when T exceeds the observational record
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Optional, Sequence

import numpy as np

from src.utils import get_logger
from .gev import (
    annual_maxima_series,
    fit_gev_annual_maxima,
    _fit_gev_1d,
    _return_level,
    STANDARD_RETURN_PERIODS,
)

logger = get_logger(__name__)

# Extended set including very long periods; confidence will be flagged
ALL_RETURN_PERIODS = (2, 5, 10, 20, 25, 50, 100, 200, 500, 1000)


@dataclass
class ReturnPeriodResult:
    return_period_years: int
    estimate_mm: float
    ci_lower_mm: float
    ci_upper_mm: float
    ci_level: float
    distribution: str
    method: str
    n_years: int
    n_events: int
    sample_size: int
    extrapolation_ratio: float
    exceeds_record: bool
    confidence: str               # High | Moderate | Low | Very low
    confidence_rationale: str
    model_uncertainty_note: str
    units: str = "mm/day (or mm per accumulation period)"

    def to_dict(self) -> dict:
        return asdict(self)


def _confidence_class(
    n_years: int,
    T: int,
    ci_width_frac: float,
    converged: bool,
) -> tuple[str, str]:
    """
    Transparent confidence rules (not arbitrary labels).

    Rules (in order):
    1. Record < 10 years → Very low for any T
    2. T > 2 * n_years → at most Low
    3. T > 5 * n_years → Very low
    4. CI width > 50 % of estimate → downgrade one class
    5. Non-converged fit → downgrade one class
    """
    ratio = T / max(n_years, 1)
    if n_years < 10:
        return "Very low", f"Record length {n_years} y < 10 y minimum"
    if ratio > 5:
        return "Very low", f"Extrapolation ratio {ratio:.1f} > 5 (T={T}, n={n_years})"
    if ratio > 2:
        conf, reason = "Low", f"Extrapolation ratio {ratio:.1f} > 2 (T={T}, n={n_years})"
    elif n_years >= 30 and ratio <= 1.5:
        conf, reason = "High", f"Record {n_years} y, modest extrapolation ratio {ratio:.1f}"
    else:
        conf, reason = "Moderate", f"Record {n_years} y, ratio {ratio:.1f}"

    if ci_width_frac > 0.5:
        order = ["Very low", "Low", "Moderate", "High"]
        idx = max(0, order.index(conf) - 1)
        conf = order[idx]
        reason += f"; wide CI ({ci_width_frac:.0%} of estimate)"
    if not converged:
        order = ["Very low", "Low", "Moderate", "High"]
        idx = max(0, order.index(conf) - 1)
        conf = order[idx]
        reason += "; fit did not fully converge"
    return conf, reason


def report_return_periods_1d(
    annual_maxima: np.ndarray,
    return_periods: Sequence[int] = ALL_RETURN_PERIODS,
    n_bootstrap: int = 200,
    ci: float = 0.90,
    random_seed: int = 42,
) -> list[ReturnPeriodResult]:
    """
    Compute return-period results for a single annual-maxima series.

    Parameters
    ----------
    annual_maxima : 1-D array of annual maximum rainfall (mm)
    """
    series = np.asarray(annual_maxima, dtype="float64")
    series = series[np.isfinite(series)]
    n_years = len(series)
    if n_years < 5:
        logger.warning("Fewer than 5 annual maxima; return levels unreliable")

    fit = _fit_gev_1d(series)
    rng = np.random.default_rng(random_seed)
    results = []

    for T in return_periods:
        est = _return_level(fit.shape, fit.loc, fit.scale, T)
        # Bootstrap CI
        boot = []
        for _ in range(n_bootstrap):
            try:
                from scipy import stats
                c = -fit.shape
                sample = stats.genextreme.rvs(
                    c, loc=fit.loc, scale=max(fit.scale, 1e-6),
                    size=max(n_years, 5), random_state=rng,
                )
                bfit = _fit_gev_1d(sample)
                boot.append(_return_level(bfit.shape, bfit.loc, bfit.scale, T))
            except Exception:
                continue
        if len(boot) >= 20:
            alpha = (1.0 - ci) / 2.0
            lo = float(np.nanpercentile(boot, 100 * alpha))
            hi = float(np.nanpercentile(boot, 100 * (1 - alpha)))
        else:
            lo, hi = np.nan, np.nan

        ci_width_frac = (hi - lo) / est if (np.isfinite(est) and est > 0 and np.isfinite(hi)) else 1.0
        ratio = T / max(n_years, 1)
        conf, rationale = _confidence_class(n_years, T, ci_width_frac, fit.converged)

        results.append(ReturnPeriodResult(
            return_period_years=int(T),
            estimate_mm=float(est) if np.isfinite(est) else float("nan"),
            ci_lower_mm=lo,
            ci_upper_mm=hi,
            ci_level=ci,
            distribution="GEV" if fit.shape != 0 else "Gumbel",
            method=fit.method,
            n_years=n_years,
            n_events=n_years,  # AMS: one event per year
            sample_size=n_years,
            extrapolation_ratio=float(ratio),
            exceeds_record=T > n_years,
            confidence=conf,
            confidence_rationale=rationale,
            model_uncertainty_note=(
                "Parametric bootstrap under GEV assumption; "
                "does not include structural model uncertainty or climate non-stationarity."
            ),
        ))
    return results


def format_return_period_table(results: list[ReturnPeriodResult]) -> str:
    """Human-readable table emphasising uncertainty."""
    lines = [
        f"{'T (y)':>6}  {'Estimate':>10}  {'CI low':>10}  {'CI high':>10}  "
        f"{'Ratio':>6}  {'Conf':>10}  Note"
    ]
    lines.append("-" * 90)
    for r in results:
        note = "EXTRAPOLATED" if r.exceeds_record else "within record"
        lines.append(
            f"{r.return_period_years:6d}  {r.estimate_mm:10.1f}  {r.ci_lower_mm:10.1f}  "
            f"{r.ci_upper_mm:10.1f}  {r.extrapolation_ratio:6.1f}  {r.confidence:>10}  {note}"
        )
    return "\n".join(lines)
