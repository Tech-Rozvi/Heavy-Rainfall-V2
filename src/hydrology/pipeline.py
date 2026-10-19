"""
Event hydrology pipeline: hyetograph → losses → excess → hydrograph.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Sequence, Union

import numpy as np

from src.hydrology.losses import (
    LossMethod,
    LossResult,
    scs_curve_number_excess,
    green_ampt_infiltration,
)
from src.hydrology.hydrograph import Hydrograph, excess_to_hydrograph, rational_peak_discharge
from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class EventHydrologyResult:
    loss: LossResult
    hydrograph: Optional[Hydrograph]
    peak_m3s: Optional[float]
    excess_total_mm: float
    precip_total_mm: float
    method_loss: str
    method_routing: str
    notes: list[str] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "loss": self.loss.to_dict(),
            "hydrograph": self.hydrograph.to_dict() if self.hydrograph else None,
            "peak_m3s": self.peak_m3s,
            "excess_total_mm": self.excess_total_mm,
            "precip_total_mm": self.precip_total_mm,
            "method_loss": self.method_loss,
            "method_routing": self.method_routing,
            "notes": self.notes,
            "parameters": self.parameters,
        }

    def to_hydraulic_forcing_series(self) -> dict[str, Any]:
        """Payload fragment for the hydraulics module (discharge boundary)."""
        if self.hydrograph is None:
            return {"type": "hydrology_event", "hydrograph": None}
        return {
            "type": "hydrology_event",
            "schema_version": "1.0",
            "times_s": self.hydrograph.times_s.tolist(),
            "discharge_m3s": self.hydrograph.discharge_m3s.tolist(),
            "peak_m3s": self.peak_m3s,
            "excess_total_mm": self.excess_total_mm,
            "method_loss": self.method_loss,
            "method_routing": self.method_routing,
            "notes": self.notes,
        }


def run_event_hydrology(
    precip_mm: Union[float, Sequence[float], np.ndarray],
    *,
    area_km2: float,
    loss_method: LossMethod = LossMethod.CURVE_NUMBER,
    curve_number: float = 75.0,
    initial_abstraction_ratio: float = 0.2,
    dt_h: float = 1.0,
    duration_h: Optional[float] = None,
    time_to_peak_h: Optional[float] = None,
    green_ampt_params: Optional[dict] = None,
    build_hydrograph: bool = True,
) -> EventHydrologyResult:
    """
    Run a single-event hydrology calculation.

    Parameters
    ----------
    precip_mm :
        - scalar total event depth (CN path), or
        - 1-D hyetograph depths per timestep (preferred), or
        - for Green–Ampt, interpret 1-D as intensity (mm/h) if
          ``green_ampt_params`` is supplied with ``as_intensity=True``.
    area_km2 : catchment / AOI area for UH scaling
    """
    notes: list[str] = []
    p = np.asarray(precip_mm, dtype="float64")

    if loss_method == LossMethod.CURVE_NUMBER:
        if p.ndim == 0 or p.size == 1:
            loss = scs_curve_number_excess(
                float(p), curve_number, initial_abstraction_ratio=initial_abstraction_ratio
            )
            # Spread excess uniformly over duration for UH
            dur = duration_h or dt_h
            n = max(1, int(round(dur / dt_h)))
            excess_series = np.full(n, float(loss.excess_mm) / n)
            notes.append(
                "Scalar event depth spread uniformly over duration for hydrograph."
            )
        else:
            # Incremental CN on cumulative precip (standard event approach per step)
            excess_series = np.zeros(len(p))
            cum_p = 0.0
            cum_q = 0.0
            cn = float(np.clip(curve_number, 30.0, 98.0))
            s = 25400.0 / cn - 254.0
            ia = initial_abstraction_ratio * s
            for i, dpi in enumerate(p.ravel()):
                dpi = max(float(dpi), 0.0) if np.isfinite(dpi) else 0.0
                cum_p += dpi
                if cum_p > ia:
                    q = (cum_p - ia) ** 2 / (cum_p - ia + s)
                else:
                    q = 0.0
                excess_series[i] = max(q - cum_q, 0.0)
                cum_q = q
            loss = LossResult(
                method=LossMethod.CURVE_NUMBER.value,
                precip_mm=p.ravel(),
                excess_mm=excess_series,
                infiltration_mm=np.maximum(p.ravel() - excess_series, 0.0),
                parameters={
                    "curve_number": cn,
                    "S_mm": s,
                    "Ia_ratio": initial_abstraction_ratio,
                },
            )
    elif loss_method == LossMethod.GREEN_AMPT:
        gap = green_ampt_params or {}
        dur = duration_h or (len(p.ravel()) * dt_h if p.size > 1 else dt_h)
        # Treat input as intensity series (mm/h)
        loss = green_ampt_infiltration(
            p.ravel() if p.size > 1 else float(p),
            duration_h=dur,
            hydraulic_conductivity_mm_h=gap.get("hydraulic_conductivity_mm_h", 3.6),
            suction_head_mm=gap.get("suction_head_mm", 100.0),
            theta_deficit=gap.get("theta_deficit", 0.2),
            dt_h=gap.get("dt_h", dt_h),
        )
        excess_series = loss.excess_mm
    elif loss_method == LossMethod.NONE:
        if p.ndim == 0:
            excess_series = np.array([float(p)])
        else:
            excess_series = np.maximum(p.ravel(), 0.0)
        loss = LossResult(
            method="none",
            precip_mm=np.asarray(excess_series),
            excess_mm=np.asarray(excess_series),
            infiltration_mm=np.zeros_like(excess_series),
        )
    else:
        raise ValueError(f"Unsupported loss method: {loss_method}")

    precip_total = float(np.nansum(loss.precip_mm))
    excess_total = float(np.nansum(loss.excess_mm))

    hydro = None
    peak = None
    routing = "none"
    if build_hydrograph and area_km2 > 0:
        hydro = excess_to_hydrograph(
            excess_series,
            area_km2=area_km2,
            dt_h=dt_h,
            time_to_peak_h=time_to_peak_h,
        )
        peak = hydro.peak_m3s
        routing = "triangular_uh"
        # Optional rational check note
        if precip_total > 0 and duration_h:
            i_mean = precip_total / max(duration_h, 1e-6)
            q_rat = rational_peak_discharge(i_mean, area_km2, runoff_coefficient=0.5)
            notes.append(
                f"Rational-method screening peak (C=0.5): {q_rat:.3f} m³/s "
                f"(not used as model output)."
            )

    logger.info(
        "Event hydrology: P=%.1f mm excess=%.1f mm peak=%s m³/s",
        precip_total, excess_total, f"{peak:.3f}" if peak is not None else "n/a",
    )
    return EventHydrologyResult(
        loss=loss,
        hydrograph=hydro,
        peak_m3s=peak,
        excess_total_mm=excess_total,
        precip_total_mm=precip_total,
        method_loss=loss.method,
        method_routing=routing,
        notes=notes,
        parameters={
            "area_km2": area_km2,
            "dt_h": dt_h,
            "curve_number": curve_number,
            "loss_method": loss_method.value if isinstance(loss_method, LossMethod) else str(loss_method),
        },
    )
