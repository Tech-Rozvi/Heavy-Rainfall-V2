"""
Rainfall loss / infiltration models.

SCS Curve Number
----------------
Standard event-based formulation (USDA NRCS):

  S = 25400/CN - 254   (mm, SI form)
  Ia = λ S             (λ default 0.2)
  Q = (P - Ia)² / (P - Ia + S)   for P > Ia, else 0

Green–Ampt (simplified capacity form)
-------------------------------------
Potential infiltration capacity:

  f = K * (1 + ψ * Δθ / F)   approximated with cumulative F

This module returns **excess rainfall** (runoff depth) and infiltration
depth.  It does not route water or compute flood depth.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Union

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

ArrayLike = Union[float, np.ndarray]


class LossMethod(str, Enum):
    CURVE_NUMBER = "curve_number"
    GREEN_AMPT = "green_ampt"
    NONE = "none"


@dataclass
class LossResult:
    method: str
    precip_mm: np.ndarray
    excess_mm: np.ndarray
    infiltration_mm: np.ndarray
    parameters: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["precip_mm"] = "array"
        d["excess_mm"] = "array"
        d["infiltration_mm"] = "array"
        return d


def scs_curve_number_excess(
    precip_mm: ArrayLike,
    curve_number: ArrayLike = 75.0,
    *,
    initial_abstraction_ratio: float = 0.2,
) -> LossResult:
    """
    SCS CN excess rainfall for an event depth (scalar or array).

    Parameters
    ----------
    precip_mm : event rainfall depth [mm]
    curve_number : CN in [30, 98] (scalar or same shape as precip)
    initial_abstraction_ratio : λ (default 0.2; some regions use 0.05)
    """
    p = np.asarray(precip_mm, dtype="float64")
    cn = np.asarray(curve_number, dtype="float64")
    cn = np.clip(cn, 30.0, 98.0)
    notes = []
    if initial_abstraction_ratio <= 0 or initial_abstraction_ratio > 0.3:
        notes.append(
            f"initial_abstraction_ratio={initial_abstraction_ratio} is outside "
            "the common 0.05–0.2 range; verify regional practice."
        )

    s = 25400.0 / cn - 254.0  # mm
    ia = initial_abstraction_ratio * s
    # Broadcast
    excess = np.where(
        p > ia,
        (p - ia) ** 2 / (p - ia + s),
        0.0,
    )
    excess = np.where(np.isfinite(p), np.maximum(excess, 0.0), np.nan)
    infil = np.where(np.isfinite(p), np.maximum(p - excess, 0.0), np.nan)

    return LossResult(
        method=LossMethod.CURVE_NUMBER.value,
        precip_mm=p,
        excess_mm=excess,
        infiltration_mm=infil,
        parameters={
            "curve_number_mean": float(np.nanmean(cn)),
            "S_mm_mean": float(np.nanmean(s)),
            "Ia_ratio": initial_abstraction_ratio,
        },
        notes=notes,
    )


def green_ampt_infiltration(
    precip_intensity_mm_h: ArrayLike,
    duration_h: float,
    *,
    hydraulic_conductivity_mm_h: float = 3.6,  # ~1e-6 m/s
    suction_head_mm: float = 100.0,
    theta_deficit: float = 0.2,
    dt_h: float = 0.1,
) -> LossResult:
    """
    Time-stepped Green–Ampt excess for a constant or series intensity.

    If ``precip_intensity_mm_h`` is a scalar, it is held constant for
    ``duration_h``.  If 1-D, each step is ``dt_h`` hours.
    """
    notes = [
        "Simplified Green–Ampt; cumulative infiltration F updated explicitly.",
        "Not a substitute for calibrated soil parameters.",
    ]
    if np.isscalar(precip_intensity_mm_h):
        n_steps = max(1, int(round(duration_h / dt_h)))
        intensity = np.full(n_steps, float(precip_intensity_mm_h))
    else:
        intensity = np.asarray(precip_intensity_mm_h, dtype="float64").ravel()
        n_steps = len(intensity)
        dt_h = duration_h / max(n_steps, 1) if duration_h > 0 else dt_h

    k = max(float(hydraulic_conductivity_mm_h), 1e-9)
    psi = max(float(suction_head_mm), 0.0)
    dtheta = max(float(theta_deficit), 1e-6)

    excess = np.zeros(n_steps)
    infil = np.zeros(n_steps)
    f_cum = 0.0
    precip = intensity * dt_h

    for i in range(n_steps):
        # Potential capacity (mm/h)
        f_pot = k * (1.0 + psi * dtheta / max(f_cum, 1e-3))
        f_act = min(max(intensity[i], 0.0), f_pot)
        infil[i] = f_act * dt_h
        excess[i] = max(precip[i] - infil[i], 0.0)
        f_cum += infil[i]

    return LossResult(
        method=LossMethod.GREEN_AMPT.value,
        precip_mm=precip,
        excess_mm=excess,
        infiltration_mm=infil,
        parameters={
            "K_mm_h": k,
            "suction_head_mm": psi,
            "theta_deficit": dtheta,
            "dt_h": dt_h,
            "n_steps": n_steps,
        },
        notes=notes,
    )


def apply_losses(
    precip_mm: ArrayLike,
    method: LossMethod = LossMethod.CURVE_NUMBER,
    **kwargs,
) -> LossResult:
    """Dispatch to the selected loss method."""
    if method == LossMethod.NONE:
        p = np.asarray(precip_mm, dtype="float64")
        return LossResult(
            method="none",
            precip_mm=p,
            excess_mm=np.where(np.isfinite(p), np.maximum(p, 0.0), np.nan),
            infiltration_mm=np.zeros_like(p, dtype="float64"),
            notes=["No losses applied; excess = precip."],
        )
    if method == LossMethod.CURVE_NUMBER:
        return scs_curve_number_excess(precip_mm, **kwargs)
    if method == LossMethod.GREEN_AMPT:
        # Green–Ampt expects intensity series; if scalar depth given, approximate
        raise ValueError(
            "For Green–Ampt use green_ampt_infiltration(intensity, duration_h=...)"
        )
    raise ValueError(f"Unknown loss method: {method}")
