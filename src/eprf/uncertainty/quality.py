"""
Transparent data-quality / confidence flags.

Thresholds are deliberately simple and documented so they can be challenged
and revised with regional evidence.  They are not arbitrary marketing labels.
"""
from __future__ import annotations

from typing import Optional

import numpy as np


def data_quality_flags(
    n_years: np.ndarray,
    n_stations_nearby: Optional[np.ndarray] = None,
    ensemble_agreement: Optional[np.ndarray] = None,
    extrapolation_distance_km: Optional[np.ndarray] = None,
    min_years_high: int = 20,
    min_years_moderate: int = 10,
    min_years_low: int = 5,
) -> np.ndarray:
    """
    Return integer confidence class per pixel:
        4 = High
        3 = Moderate
        2 = Low
        1 = Very low

    Primary driver is record length (n_years of annual maxima).
    Optional modifiers: station density, ensemble agreement, distance from
    observations.
    """
    n = np.asarray(n_years, dtype="float64")
    flags = np.ones(n.shape, dtype=int)  # default very low

    flags = np.where(n >= min_years_low, 2, flags)
    flags = np.where(n >= min_years_moderate, 3, flags)
    flags = np.where(n >= min_years_high, 4, flags)

    # Downgrade if far from any station
    if extrapolation_distance_km is not None:
        d = np.asarray(extrapolation_distance_km)
        flags = np.where(d > 100, np.minimum(flags, 2), flags)
        flags = np.where(d > 250, 1, flags)

    # Upgrade slightly with good station density
    if n_stations_nearby is not None:
        s = np.asarray(n_stations_nearby)
        flags = np.where((s >= 3) & (flags >= 3), np.minimum(flags + 0, 4), flags)

    # Ensemble disagreement downgrades
    if ensemble_agreement is not None:
        agr = np.asarray(ensemble_agreement)
        flags = np.where(agr < 0.5, np.minimum(flags, 2), flags)

    return flags


CONFIDENCE_LABELS = {
    4: "High",
    3: "Moderate",
    2: "Low",
    1: "Very low",
}
