"""
Intensity-Duration-Frequency (IDF) and Depth-Duration-Frequency helpers.

CRITICAL LIMITATION
-------------------
When only daily precipitation is available, durations shorter than 24 h
cannot be observed.  This module will refuse to invent sub-daily IDF
values from daily data without an explicit scaling method that the user
opts into, and will always label such values as estimated.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional, Sequence

import numpy as np

from src.utils import get_logger
from src.eprf.extremes.return_period_report import report_return_periods_1d

logger = get_logger(__name__)

# Durations that are scientifically defensible from daily data
SUPPORTED_DURATIONS_DAILY = (24, 48, 72)  # hours

# Sub-daily durations require sub-daily observations or an explicit scaling model
SUBDAILY_DURATIONS = (1/12, 1/6, 0.25, 0.5, 1, 2, 3, 6, 12)  # hours


@dataclass
class IDFCurve:
    duration_hours: float
    return_periods: list[int]
    intensities_mm_h: list[float]
    depths_mm: list[float]
    ci_lower_mm_h: list[float]
    ci_upper_mm_h: list[float]
    confidence: list[str]
    source: str                          # "observed_daily" | "estimated_subdaily" | "subdaily_obs"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def compute_idf_from_daily(
    daily_precip: np.ndarray,
    return_periods: Sequence[int] = (2, 5, 10, 25, 50, 100),
    durations_hours: Sequence[float] = SUPPORTED_DURATIONS_DAILY,
    allow_subdaily_estimate: bool = False,
    n_bootstrap: int = 100,
) -> list[IDFCurve]:
    """
    Build IDF/DDF curves from a 1-D or (T,) daily series.

    For duration D hours where D is a multiple of 24, rolling sums of
    D/24 days are used as the block-maxima series.

    Sub-daily durations are only produced if allow_subdaily_estimate=True,
    and are labelled as estimates (not observations).
    """
    series = np.asarray(daily_precip, dtype="float64").ravel()
    series = series[np.isfinite(series)]
    curves = []

    for dur_h in durations_hours:
        notes = []
        if dur_h < 24:
            if not allow_subdaily_estimate:
                logger.warning(
                    "Skipping duration %.2f h: sub-daily IDF requires "
                    "allow_subdaily_estimate=True and is labelled estimated.",
                    dur_h,
                )
                continue
            notes.append(
                "ESTIMATED sub-daily intensity derived from daily data. "
                "Not an observed IDF value. Use only with explicit acknowledgement."
            )
            source = "estimated_subdaily"
            # Crude constant-intensity assumption: depth_24h / 24 * duration
            # This is a placeholder scaling; regional relationships should replace it.
            am = _annual_max_rolling(series, window_days=1)
            results = report_return_periods_1d(am, return_periods=return_periods, n_bootstrap=n_bootstrap)
            scale = dur_h / 24.0
            depths = [r.estimate_mm * scale for r in results]
            intensities = [d / dur_h for d in depths]
            ci_lo = [r.ci_lower_mm * scale / dur_h for r in results]
            ci_hi = [r.ci_upper_mm * scale / dur_h for r in results]
            conf = [r.confidence for r in results]
        else:
            window_days = max(1, int(round(dur_h / 24.0)))
            am = _annual_max_rolling(series, window_days=window_days)
            results = report_return_periods_1d(am, return_periods=return_periods, n_bootstrap=n_bootstrap)
            depths = [r.estimate_mm for r in results]
            intensities = [d / dur_h for d in depths]
            ci_lo = [r.ci_lower_mm / dur_h for r in results]
            ci_hi = [r.ci_upper_mm / dur_h for r in results]
            conf = [r.confidence for r in results]
            source = "observed_daily"
            notes.append(f"Based on {window_days}-day annual maxima from daily observations.")

        curves.append(IDFCurve(
            duration_hours=float(dur_h),
            return_periods=list(return_periods),
            intensities_mm_h=intensities,
            depths_mm=depths,
            ci_lower_mm_h=ci_lo,
            ci_upper_mm_h=ci_hi,
            confidence=conf,
            source=source,
            notes=notes,
        ))
    return curves


def _annual_max_rolling(daily: np.ndarray, window_days: int = 1) -> np.ndarray:
    """Annual maxima of rolling window sums."""
    if window_days <= 1:
        # Simple annual blocks of 365 days
        n_years = len(daily) // 365
        if n_years < 1:
            return np.array([np.nanmax(daily)])
        am = []
        for i in range(n_years):
            slab = daily[i * 365:(i + 1) * 365]
            am.append(np.nanmax(slab))
        return np.asarray(am, dtype="float64")

    # Rolling sum
    kernel = np.ones(window_days)
    rolled = np.convolve(np.nan_to_num(daily, nan=0.0), kernel, mode="valid")
    n_years = len(rolled) // 365
    if n_years < 1:
        return np.array([np.nanmax(rolled)])
    am = []
    for i in range(n_years):
        slab = rolled[i * 365:(i + 1) * 365]
        am.append(np.nanmax(slab))
    return np.asarray(am, dtype="float64")
