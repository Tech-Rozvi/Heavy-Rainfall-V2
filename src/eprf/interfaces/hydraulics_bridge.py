"""
Bridge from rainfall design storms to the hydraulics module.

Contract rules
--------------
1. Rainfall side emits RainfallForcing only (never flood depth).
2. This bridge is the supported path into src.hydraulics.
3. Depth products returned as HydraulicResult are labelled provisional
   until event-validated for the domain.
4. run_solver=False returns metadata only — no fabricated depths.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np

from src.utils import get_logger
from src.eprf.interfaces.contracts import (
    RainfallForcing,
    HydraulicResult,
    ModuleOutputMeta,
)

logger = get_logger(__name__)

PROVISIONAL_NOTE = (
    "Flood depth / inundation products are PROVISIONAL. They have not been "
    "validated against observed flood events in this repository. Do not use "
    "as regulatory design flood surfaces without independent validation."
)


class _HyetographForcing:
    """Minimal pluvial forcing adapter: RainfallForcing hyetograph → rain_at()."""

    def __init__(self, forcing: RainfallForcing, shape: tuple[int, int]):
        self.hyeto = np.asarray(forcing.hyetograph_mm, dtype="float64").ravel()
        self.dt_h = float(forcing.timestep_hours)
        self.shape = shape
        self.total_duration_s = len(self.hyeto) * self.dt_h * 3600.0

    def rain_at(self, t: float, state) -> np.ndarray:
        if self.dt_h <= 0 or len(self.hyeto) == 0:
            return np.zeros(self.shape, dtype="float64")
        idx = int(t // (self.dt_h * 3600.0))
        if idx < 0 or idx >= len(self.hyeto):
            intensity_mm_h = 0.0
        else:
            intensity_mm_h = float(self.hyeto[idx]) / self.dt_h
        rate_m_s = intensity_mm_h / 3_600_000.0
        return np.full(self.shape, rate_m_s, dtype="float64")

    def infiltration_at(self, t: float, state) -> np.ndarray:
        return np.zeros(self.shape, dtype="float64")


def rainfall_forcing_to_hydraulic_run(
    forcing: RainfallForcing,
    dem: np.ndarray,
    bounds: tuple[float, float, float, float],
    *,
    dx: float = 30.0,
    dy: float = 30.0,
    transform: Any = None,
    output_dir: Optional[Path] = None,
    run_solver: bool = True,
    duration_s: Optional[float] = None,
    manning_n: float = 0.04,
    use_direct_solver: bool = True,
) -> HydraulicResult:
    """
    Translate RainfallForcing into a hydraulics run and return HydraulicResult.

    Preferred path (use_direct_solver=True): drive ShallowWater2D with the
    hyetograph embedded in RainfallForcing.
    """
    forcing.assert_not_flood_depth()
    notes = [
        PROVISIONAL_NOTE,
        f"Driven by rainfall forcing depth={forcing.total_depth_mm:.1f} mm, "
        f"duration={forcing.duration_hours:.2f} h, pattern={forcing.temporal_pattern}.",
    ]
    if forcing.meta.return_period_years is not None:
        notes.append(f"Design return period T={forcing.meta.return_period_years} years.")

    meta = ModuleOutputMeta(
        aoi_id=forcing.meta.aoi_id,
        module="hydraulics",
        model_version=forcing.meta.model_version,
        data_kind="hydraulically_simulated",
        return_period_years=forcing.meta.return_period_years,
        confidence=forcing.meta.confidence or "low",
        crs=forcing.meta.crs,
        units={"max_depth_m": "m", "velocity_m_s": "m/s"},
        notes=list(notes),
    )

    if not run_solver:
        meta.notes.append("Solver not executed (run_solver=False). No flood depths produced.")
        return HydraulicResult(
            meta=meta,
            forcing_aoi_id=forcing.meta.aoi_id,
            forcing_return_period=forcing.meta.return_period_years,
            validation_status="provisional",
            validation_notes=list(notes) + ["No solver run."],
            product_labels={},
        )

    dem = np.asarray(dem, dtype="float64")
    if dem.ndim != 2:
        raise ValueError("DEM must be 2-D")

    max_depth = None
    extent = None
    solver_notes: list[str] = []

    if use_direct_solver:
        try:
            max_depth, extent, solver_notes = _run_direct_solver(
                dem, forcing, dx=dx, dy=dy, manning_n=manning_n, duration_s=duration_s
            )
        except Exception as exc:
            logger.warning("Direct solver path failed (%s); trying forecast_run fallback", exc)
            solver_notes.append(f"Direct solver failed: {exc}")
            use_direct_solver = False

    if not use_direct_solver and max_depth is None:
        max_depth, extent, fb_notes = _run_forecast_fallback(
            dem, bounds, dx, dy, transform, output_dir, forcing
        )
        solver_notes.extend(fb_notes)

    meta.notes.extend(solver_notes)
    return HydraulicResult(
        meta=meta,
        max_depth_m=max_depth,
        flood_extent=extent,
        forcing_aoi_id=forcing.meta.aoi_id,
        forcing_return_period=forcing.meta.return_period_years,
        validation_status="provisional",
        validation_notes=list(notes) + solver_notes,
    )


def _run_direct_solver(
    dem: np.ndarray,
    forcing: RainfallForcing,
    *,
    dx: float,
    dy: float,
    manning_n: float,
    duration_s: Optional[float],
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    from src.hydraulics.solver2d import ShallowWater2D, SolverConfig

    cfg = SolverConfig(
        dx=float(dx),
        dy=float(dy),
        manning_n=float(manning_n),
        max_steps=50_000,
    )
    solver = ShallowWater2D(dem, cfg)
    pluvial = _HyetographForcing(forcing, dem.shape)
    dur = float(duration_s) if duration_s is not None else max(
        pluvial.total_duration_s * 1.25, 600.0
    )
    dur = min(dur, 6 * 3600.0)
    state = solver.run(duration_s=dur, forcing=pluvial)
    hmax = np.asarray(state.h_max if state.h_max is not None else state.h, dtype="float64")
    extent = (hmax > 0.05).astype("float64")
    notes = [
        f"Direct ShallowWater2D run duration_s={dur:.1f}, steps={state.step}.",
        "Depth product label: provisional_flood_depth.",
    ]
    logger.info("Hydraulics direct run complete: max depth=%.3f m", float(np.nanmax(hmax)))
    return hmax, extent, notes


def _run_forecast_fallback(
    dem, bounds, dx, dy, transform, output_dir, forcing
) -> tuple[Optional[np.ndarray], Optional[np.ndarray], list[str]]:
    notes = [
        "Fallback path: forecast_run does not consume full RainfallForcing hyetograph; "
        "results are still provisional."
    ]
    try:
        from src.hydraulics.forecast_run import run_forecast_flood
        out_dir = Path(output_dir or "outputs/rasters/forecast")
        out_dir.mkdir(parents=True, exist_ok=True)
        result = run_forecast_flood(
            dem,
            bounds,
            dx=dx,
            dy=dy,
            transform=transform,
            forecast_days=max(1, int(np.ceil(forcing.duration_hours / 24.0))),
            output_dir=out_dir,
        )
        if isinstance(result, dict):
            return result.get("hmax"), result.get("extent"), notes
    except Exception as exc:
        notes.append(f"forecast_run fallback failed: {exc}")
    return None, None, notes


def label_depth_product(
    depth_m: np.ndarray,
    *,
    validation_status: str = "provisional",
    threshold_m: float = 0.05,
) -> dict:
    """Attach standard product labels to a depth array for GIS/API delivery."""
    arr = np.asarray(depth_m, dtype="float64")
    return {
        "product": "flood_depth",
        "units": "m",
        "validation_status": validation_status,
        "label": "provisional_flood_depth" if validation_status == "provisional" else "flood_depth",
        "wet_fraction": float(np.nanmean(arr > threshold_m)) if arr.size else 0.0,
        "max_m": float(np.nanmax(arr)) if arr.size else None,
        "mean_wet_m": float(np.nanmean(arr[arr > threshold_m])) if np.any(arr > threshold_m) else 0.0,
        "disclaimer": (
            PROVISIONAL_NOTE
            if validation_status == "provisional"
            else (
                "Event-validated against supplied observations for a named event. "
                "Not automatically validated for other events or design return periods."
                if validation_status == "event_validated"
                else ""
            )
        ),
    }
