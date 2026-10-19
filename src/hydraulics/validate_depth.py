"""
Event-based flood depth validation.

Compares simulated depth fields to user-supplied observations:
  - high-water marks / point depths (required for event_validated)
  - optional binary inundation footprints (CSI / F1)

Does **not** fabricate observations. Does **not** set event_validated
unless explicit pass criteria are met via evaluate_event_depth().
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Sequence

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

ALLOWED_STATUS = ("provisional", "event_validated", "research_only")


@dataclass
class HighWaterMark:
    """Single surveyed or reported water depth observation."""
    x: float
    y: float
    depth_m: float
    mark_id: str = ""
    source: str = "user"
    notes: str = ""


@dataclass
class DepthPointComparison:
    mark_id: str
    x: float
    y: float
    observed_m: float
    simulated_m: Optional[float]
    error_m: Optional[float]
    inside_grid: bool


@dataclass
class FootprintScores:
    csi: Optional[float]
    precision: Optional[float]
    recall: Optional[float]
    f1: Optional[float]
    hits: int
    false_alarms: int
    misses: int
    threshold_m: float


@dataclass
class DepthValidationReport:
    """Structured validation outcome for one event / AOI."""
    event_id: str
    n_marks: int
    point_metrics: dict[str, Any]
    point_comparisons: list[dict] = field(default_factory=list)
    footprint: Optional[dict] = None
    passed: bool = False
    validation_status: str = "provisional"
    criteria: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    observation_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _sample_depth(
    depth_m: np.ndarray,
    x: float,
    y: float,
    *,
    transform: Any = None,
    bounds: Optional[tuple[float, float, float, float]] = None,
) -> tuple[Optional[float], bool]:
    arr = np.asarray(depth_m, dtype="float64")
    if arr.ndim != 2:
        raise ValueError("depth_m must be 2-D")
    ny, nx = arr.shape
    if transform is not None:
        try:
            col, row = ~transform * (x, y)
            r, c = int(round(row)), int(round(col))
        except Exception:
            return None, False
    elif bounds is not None:
        minx, miny, maxx, maxy = bounds
        if maxx == minx or maxy == miny:
            return None, False
        c = int(round((x - minx) / (maxx - minx) * (nx - 1)))
        r = int(round((maxy - y) / (maxy - miny) * (ny - 1)))
    else:
        c, r = int(round(x)), int(round(y))
    if r < 0 or c < 0 or r >= ny or c >= nx:
        return None, False
    val = arr[r, c]
    if not np.isfinite(val):
        return None, True
    return float(val), True


def compare_high_water_marks(
    depth_m: np.ndarray,
    marks: Sequence[HighWaterMark],
    *,
    transform: Any = None,
    bounds: Optional[tuple[float, float, float, float]] = None,
) -> tuple[list[DepthPointComparison], dict[str, Any]]:
    """Sample simulated depth at HWM locations and compute error metrics."""
    comps: list[DepthPointComparison] = []
    errors = []
    obs_list = []
    sim_list = []
    for i, m in enumerate(marks):
        sim, inside = _sample_depth(
            depth_m, m.x, m.y, transform=transform, bounds=bounds
        )
        err = None if sim is None else float(sim - m.depth_m)
        if err is not None:
            errors.append(err)
            obs_list.append(m.depth_m)
            sim_list.append(sim)
        comps.append(
            DepthPointComparison(
                mark_id=m.mark_id or f"hwm_{i}",
                x=m.x,
                y=m.y,
                observed_m=float(m.depth_m),
                simulated_m=sim,
                error_m=err,
                inside_grid=inside,
            )
        )
    metrics: dict[str, Any] = {
        "n_compared": len(errors),
        "n_outside_or_nodata": len(marks) - len(errors),
        "bias_m": float(np.mean(errors)) if errors else None,
        "mae_m": float(np.mean(np.abs(errors))) if errors else None,
        "rmse_m": float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
        "max_abs_error_m": float(np.max(np.abs(errors))) if errors else None,
    }
    return comps, metrics


def compare_inundation_footprint(
    depth_m: np.ndarray,
    observed_wet: np.ndarray,
    *,
    threshold_m: float = 0.05,
) -> FootprintScores:
    """
    Binary contingency scores on a common grid.

    observed_wet: boolean or 0/1 array, same shape as depth_m (True = observed inundation).
    """
    sim = np.asarray(depth_m, dtype="float64")
    obs = np.asarray(observed_wet)
    if sim.shape != obs.shape:
        raise ValueError(f"shape mismatch sim {sim.shape} vs obs {obs.shape}")
    sim_wet = np.isfinite(sim) & (sim > threshold_m)
    obs_wet = obs.astype(bool)
    hits = int(np.sum(sim_wet & obs_wet))
    fa = int(np.sum(sim_wet & ~obs_wet))
    misses = int(np.sum(~sim_wet & obs_wet))
    denom_csi = hits + fa + misses
    csi = hits / denom_csi if denom_csi else None
    prec = hits / (hits + fa) if (hits + fa) else None
    rec = hits / (hits + misses) if (hits + misses) else None
    f1 = None
    if prec is not None and rec is not None and (prec + rec) > 0:
        f1 = 2 * prec * rec / (prec + rec)
    return FootprintScores(
        csi=csi,
        precision=prec,
        recall=rec,
        f1=f1,
        hits=hits,
        false_alarms=fa,
        misses=misses,
        threshold_m=threshold_m,
    )


def evaluate_event_depth(
    depth_m: np.ndarray,
    marks: Sequence[HighWaterMark],
    *,
    event_id: str = "event",
    transform: Any = None,
    bounds: Optional[tuple[float, float, float, float]] = None,
    observed_wet: Optional[np.ndarray] = None,
    footprint_threshold_m: float = 0.05,
    # Pass criteria (document before looking at results)
    min_marks: int = 3,
    max_mae_m: float = 0.30,
    max_abs_bias_m: float = 0.30,
    min_csi: Optional[float] = None,
    require_footprint: bool = False,
) -> DepthValidationReport:
    """
    Evaluate simulated depth against observations and decide pass/fail.

    event_validated is granted only when:
      - at least min_marks points compared successfully
      - MAE <= max_mae_m
      - |bias| <= max_abs_bias_m
      - if require_footprint or observed_wet given with min_csi: CSI >= min_csi
    """
    notes: list[str] = []
    sources = sorted({(m.source or "user") for m in marks})
    if len(marks) < min_marks:
        notes.append(
            f"Only {len(marks)} high-water marks supplied; need >= {min_marks} for event_validated."
        )

    comps, metrics = compare_high_water_marks(
        depth_m, marks, transform=transform, bounds=bounds
    )
    footprint_dict = None
    csi_ok = True
    if observed_wet is not None:
        fp = compare_inundation_footprint(
            depth_m, observed_wet, threshold_m=footprint_threshold_m
        )
        footprint_dict = asdict(fp)
        if min_csi is not None:
            csi_ok = fp.csi is not None and fp.csi >= min_csi
            if not csi_ok:
                notes.append(
                    f"Footprint CSI {fp.csi} below minimum {min_csi}."
                )
        elif require_footprint:
            notes.append("Footprint provided but min_csi not set; CSI reported only.")
    elif require_footprint:
        csi_ok = False
        notes.append("require_footprint=True but observed_wet not provided.")

    n_ok = int(metrics.get("n_compared") or 0)
    mae = metrics.get("mae_m")
    bias = metrics.get("bias_m")
    mae_ok = mae is not None and mae <= max_mae_m
    bias_ok = bias is not None and abs(bias) <= max_abs_bias_m
    count_ok = n_ok >= min_marks

    passed = bool(count_ok and mae_ok and bias_ok and csi_ok)
    if not count_ok:
        notes.append(f"Insufficient compared marks ({n_ok} < {min_marks}).")
    if mae is None:
        notes.append("MAE undefined (no overlapping marks).")
    elif not mae_ok:
        notes.append(f"MAE {mae:.3f} m exceeds max_mae_m={max_mae_m}.")
    if bias is None:
        notes.append("Bias undefined.")
    elif not bias_ok:
        notes.append(f"|bias| {abs(bias):.3f} m exceeds max_abs_bias_m={max_abs_bias_m}.")

    status = "event_validated" if passed else "provisional"
    if passed:
        notes.append(
            "PASSED event criteria. Status event_validated applies to this event "
            "depth field only — not automatically to design return-period maps."
        )
    else:
        notes.append("FAILED or incomplete — depth remains provisional.")

    criteria = {
        "min_marks": min_marks,
        "max_mae_m": max_mae_m,
        "max_abs_bias_m": max_abs_bias_m,
        "min_csi": min_csi,
        "require_footprint": require_footprint,
    }
    report = DepthValidationReport(
        event_id=event_id,
        n_marks=len(marks),
        point_metrics=metrics,
        point_comparisons=[asdict(c) for c in comps],
        footprint=footprint_dict,
        passed=passed,
        validation_status=status,
        criteria=criteria,
        notes=notes,
        observation_sources=sources,
    )
    logger.info(
        "Depth validation event=%s passed=%s status=%s mae=%s n=%s",
        event_id, passed, status, mae, n_ok,
    )
    return report


def apply_validation_to_labels(
    depth_m: np.ndarray,
    report: DepthValidationReport,
    *,
    threshold_m: float = 0.05,
) -> dict:
    """Product labels consistent with validation outcome."""
    from src.eprf.interfaces.hydraulics_bridge import label_depth_product

    labels = label_depth_product(
        depth_m,
        validation_status=report.validation_status,
        threshold_m=threshold_m,
    )
    labels["event_id"] = report.event_id
    labels["validation_passed"] = report.passed
    labels["point_metrics"] = report.point_metrics
    if report.validation_status == "event_validated":
        labels["disclaimer"] = (
            f"Event-validated for event_id={report.event_id} against "
            f"{report.n_marks} high-water marks (sources={report.observation_sources}). "
            "Does not imply regulatory design-flood approval or validation of other events."
        )
    return labels
