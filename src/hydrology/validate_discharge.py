"""
Discharge validation hooks.

Compares a simulated hydrograph to observed Q(t) when the user supplies
observations.  Does not fabricate gauges or claim skill without data.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional, Sequence

import numpy as np

from src.hydrology.hydrograph import Hydrograph
from src.eprf.validation.metrics import evaluate_precipitation
from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class DischargeValidationReport:
    n_points: int
    metrics: dict
    peak_obs_m3s: Optional[float]
    peak_sim_m3s: Optional[float]
    peak_error_pct: Optional[float]
    volume_obs_m3: Optional[float]
    volume_sim_m3: Optional[float]
    volume_error_pct: Optional[float]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def validate_hydrograph(
    observed: Hydrograph,
    simulated: Hydrograph,
) -> DischargeValidationReport:
    """
    Interpolate simulated Q onto observed times and compute error metrics.

    Uses the same continuous metrics helper as rainfall (MAE, RMSE, bias, corr, NSE, KGE)
    applied to discharge series.
    """
    notes = []
    if len(observed.times_s) < 3:
        notes.append("Fewer than 3 observed points; metrics unstable.")

    t = observed.times_s
    q_obs = observed.discharge_m3s
    q_sim = np.array([simulated.q_at(float(tt)) for tt in t])

    metrics = evaluate_precipitation(q_obs, q_sim)  # same formulae; units m³/s

    peak_obs = float(np.nanmax(q_obs)) if len(q_obs) else None
    peak_sim = float(np.nanmax(q_sim)) if len(q_sim) else None
    peak_err = None
    if peak_obs and peak_obs > 0 and peak_sim is not None:
        peak_err = 100.0 * (peak_sim - peak_obs) / peak_obs

    vol_obs = observed.volume_m3
    vol_sim = float(np.trapezoid(q_sim, t)) if len(t) > 1 else None
    vol_err = None
    if vol_obs and vol_obs > 0 and vol_sim is not None:
        vol_err = 100.0 * (vol_sim - vol_obs) / vol_obs

    notes.append(
        "Discharge validation requires user-supplied observations; "
        "this report is NOT a claim of regional model skill."
    )
    return DischargeValidationReport(
        n_points=int(np.sum(np.isfinite(q_obs) & np.isfinite(q_sim))),
        metrics=metrics,
        peak_obs_m3s=peak_obs,
        peak_sim_m3s=peak_sim,
        peak_error_pct=peak_err,
        volume_obs_m3=vol_obs,
        volume_sim_m3=vol_sim,
        volume_error_pct=vol_err,
        notes=notes,
    )


def hydrograph_from_csv_times_q(
    times_s: Sequence[float],
    discharge_m3s: Sequence[float],
) -> Hydrograph:
    """Helper to build an observed hydrograph from arrays."""
    return Hydrograph.from_arrays(times_s, discharge_m3s, metadata={"role": "observed"})
