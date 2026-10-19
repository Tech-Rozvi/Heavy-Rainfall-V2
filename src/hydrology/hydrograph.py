"""
Hydrograph representation and simple rainfall–runoff transforms.

Provides:
- Hydrograph container Q(t) [m³/s] compatible with hydraulics forcing
- Triangular unit hydrograph convolution of excess rainfall
- Rational method peak discharge (screening only)
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Sequence

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class Hydrograph:
    """Piecewise-linear discharge Q(t) [m³/s]."""

    times_s: np.ndarray
    discharge_m3s: np.ndarray
    metadata: Optional[dict] = None

    def __post_init__(self) -> None:
        self.times_s = np.asarray(self.times_s, dtype="float64")
        self.discharge_m3s = np.asarray(self.discharge_m3s, dtype="float64")
        if self.times_s.shape != self.discharge_m3s.shape:
            raise ValueError("times_s and discharge_m3s must have the same shape")
        if len(self.times_s) < 1:
            raise ValueError("Hydrograph must contain at least one sample")

    def q_at(self, t: float) -> float:
        ts, qs = self.times_s, self.discharge_m3s
        t = float(t)
        if t <= ts[0]:
            return float(qs[0])
        if t >= ts[-1]:
            return float(qs[-1])
        return float(np.interp(t, ts, qs))

    @property
    def peak_m3s(self) -> float:
        return float(np.nanmax(self.discharge_m3s))

    @property
    def volume_m3(self) -> float:
        if len(self.times_s) < 2:
            return 0.0
        return float(np.trapezoid(self.discharge_m3s, self.times_s))

    @classmethod
    def from_arrays(
        cls,
        times_s: Sequence[float],
        q_m3s: Sequence[float],
        metadata: Optional[dict] = None,
    ) -> "Hydrograph":
        return cls(
            np.asarray(times_s, dtype="float64"),
            np.asarray(q_m3s, dtype="float64"),
            metadata=metadata,
        )

    def to_dict(self) -> dict:
        return {
            "times_s": self.times_s.tolist(),
            "discharge_m3s": self.discharge_m3s.tolist(),
            "peak_m3s": self.peak_m3s,
            "volume_m3": self.volume_m3,
            "metadata": self.metadata,
        }


def rational_peak_discharge(
    intensity_mm_h: float,
    area_km2: float,
    runoff_coefficient: float = 0.5,
) -> float:
    """
    Rational method peak discharge [m³/s].

    Q = C * i * A / 3.6
    with i in mm/h, A in km².

    Screening-level only; not a substitute for unit-hydrograph or calibrated models.
    """
    c = float(np.clip(runoff_coefficient, 0.0, 1.0))
    return c * float(intensity_mm_h) * float(area_km2) / 3.6


def triangular_unit_hydrograph(
    area_km2: float,
    time_to_peak_h: float,
    base_time_h: Optional[float] = None,
    dt_h: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """
    NRCS-style triangular unit hydrograph for 1 mm of excess over the catchment.

    Returns (times_h, q_m3s_per_mm_excess).
    """
    tp = max(float(time_to_peak_h), dt_h)
    tb = float(base_time_h) if base_time_h is not None else 2.67 * tp
    tb = max(tb, tp + dt_h)
    # Peak of UH for 1 mm excess: Qp = 0.208 * A / tp  (A in km², tp in h)
    # Metric approximation used in many textbooks (qp in m³/s per mm)
    qp = 0.208 * float(area_km2) / tp

    times = np.arange(0.0, tb + dt_h, dt_h)
    q = np.zeros_like(times)
    for i, t in enumerate(times):
        if t <= tp:
            q[i] = qp * (t / tp)
        elif t <= tb:
            q[i] = qp * (tb - t) / (tb - tp)
        else:
            q[i] = 0.0
    return times, q


def excess_to_hydrograph(
    excess_mm: Sequence[float] | np.ndarray,
    *,
    area_km2: float,
    dt_h: float = 1.0,
    time_to_peak_h: Optional[float] = None,
    base_time_h: Optional[float] = None,
) -> Hydrograph:
    """
    Convolve excess rainfall increments with a triangular unit hydrograph.

    Parameters
    ----------
    excess_mm : excess depth per timestep [mm]
    area_km2 : contributing area
    dt_h : timestep of excess series [hours]
    time_to_peak_h : if None, defaults to dt_h (minimum response)
    """
    excess = np.asarray(excess_mm, dtype="float64").ravel()
    excess = np.where(np.isfinite(excess), np.maximum(excess, 0.0), 0.0)
    tp = float(time_to_peak_h) if time_to_peak_h is not None else max(dt_h, 0.1)
    uh_t, uh_q = triangular_unit_hydrograph(
        area_km2, tp, base_time_h=base_time_h, dt_h=min(dt_h, tp / 2.0)
    )
    # Resample UH to dt_h
    n_uh = max(2, int(round(uh_t[-1] / dt_h)) + 1)
    t_reg = np.arange(n_uh) * dt_h
    uh_reg = np.interp(t_reg, uh_t, uh_q)

    # Convolution: each excess pulse contributes excess[i] * UH
    q = np.convolve(excess, uh_reg)
    times_s = np.arange(len(q)) * dt_h * 3600.0
    meta = {
        "method": "triangular_uh_convolution",
        "area_km2": area_km2,
        "dt_h": dt_h,
        "time_to_peak_h": tp,
        "excess_total_mm": float(np.sum(excess)),
    }
    return Hydrograph(times_s=times_s, discharge_m3s=q, metadata=meta)
