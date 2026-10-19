"""
pipeline.py — EVT → CMIP6 → multi-peril SWE → GeoTIFF depth products.

Exports peak water depth [m] for T = 10, 50, 100, 250, 500 as GIS-ready
GeoTIFFs under ``output_dir``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from src.utils import get_logger
from src.statistics.evt_return_periods import (
    STANDARD_RETURN_PERIODS,
    precip_return_period_maps,
    design_storm_hyetograph_mm_h,
    depth_return_period_from_scenario_depths,
)
from src.climate.cmip6_projection import ClimateHorizon, project_design_storms
from .solver2d import ShallowWater2D, SolverConfig
from .multi_peril import Hydrograph, build_forcing_from_layers

logger = get_logger(__name__)


def export_depth_geotiffs(
    depth_maps: dict[str, np.ndarray],
    output_dir: str | Path,
    transform: Any,
    crs: str = "EPSG:4326",
    nodata: float = -9999.0,
    validation_status: str = "provisional",
    event_id: str = "",
) -> list[Path]:
    """Write each depth_* array to a float32 GeoTIFF with validation tags."""
    import rasterio
    from rasterio.transform import Affine

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if transform is None:
        transform = Affine.identity()
    written: list[Path] = []
    for key, arr in depth_maps.items():
        if not isinstance(arr, np.ndarray):
            continue
        data = np.where(np.isfinite(arr), arr, nodata).astype("float32")
        path = output_dir / f"{key}.tif"
        profile = {
            "driver": "GTiff",
            "height": data.shape[0],
            "width": data.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": crs,
            "transform": transform,
            "nodata": nodata,
            "compress": "deflate",
            "tiled": True,
        }
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data, 1)
            label = (
                "event_validated_flood_depth"
                if validation_status == "event_validated"
                else "provisional_flood_depth"
            )
            disc = (
                f"Event-validated flood depth for event_id={event_id}. "
                "Not a regulatory design product by itself."
                if validation_status == "event_validated"
                else (
                    "PROVISIONAL flood depth — not event-validated. "
                    "Do not use as regulatory design flood surfaces without independent validation."
                )
            )
            dst.update_tags(
                description=f"Peak flood depth from 2D SWE [metres] — {validation_status}",
                units="m",
                product=key,
                validation_status=validation_status,
                product_label=label,
                event_id=event_id or "",
                disclaimer=disc,
            )
        written.append(path)
        logger.info("Wrote %s", path)
    return written


def run_hydraulic_return_periods(
    dem: np.ndarray,
    *,
    daily_precip: Optional[np.ndarray] = None,
    dx: float = 30.0,
    dy: float = 30.0,
    transform: Any = None,
    crs: str = "EPSG:4326",
    manning: float | np.ndarray = 0.04,
    cn: float | np.ndarray = 75.0,
    return_periods: Sequence[int] = STANDARD_RETURN_PERIODS,
    storm_duration_h: float = 24.0,
    evt_method: str = "gumbel",
    rain_fallback_mm_day: Optional[dict[int, float]] = None,
    river_mask: Optional[np.ndarray] = None,
    river_path: Optional[str] = None,
    river_peak_m3s: float = 0.0,
    coastal_mask: Optional[np.ndarray] = None,
    coastal_level_series: Any = None,
    coastal_dt_s: float = 60.0,
    climate_horizon: Optional[ClimateHorizon] = None,
    cmip6_delta_table: Optional[dict] = None,
    spatial_delta_pct: Optional[np.ndarray] = None,
    allow_default_climate_factors: bool = False,
    solver_hours: Optional[float] = None,
    output_dir: Optional[str | Path] = "outputs/rasters/hydraulics",
    export_geotiff: bool = True,
) -> dict[str, Any]:
    dem = np.asarray(dem, dtype="float64")
    if dem.ndim != 2:
        raise ValueError("dem must be 2-D")

    if daily_precip is not None and getattr(daily_precip, "ndim", 0) == 3 and daily_precip.shape[0] >= 365:
        rp_rain = precip_return_period_maps(
            daily_precip, return_periods=return_periods, method=evt_method
        )
        design_mm_day = {
            int(T): float(np.nanmean(rp_rain[f"T{int(T)}"])) for T in return_periods
        }
    else:
        logger.warning("Fallback design rainfall (no long precip stack).")
        fb = rain_fallback_mm_day or {
            10: 80.0, 50: 120.0, 100: 150.0, 250: 190.0, 500: 220.0
        }
        design_mm_day = {int(T): float(fb.get(int(T), 100.0)) for T in return_periods}
        rp_rain = None

    climate_meta = None
    if climate_horizon is not None:
        proj = project_design_storms(
            design_mm_day,
            climate_horizon,
            delta_table=cmip6_delta_table,
            spatial_delta_pct=spatial_delta_pct,
            allow_default_factors=allow_default_climate_factors,
            storm_duration_h=storm_duration_h,
            return_periods=return_periods,
        )
        design_mm_day = proj["future_mm_day"]
        climate_meta = {
            "ssp": proj["ssp"],
            "horizon_year": proj["horizon_year"],
            "scale_factor": proj.get("scale_factor_scalar", proj["scale_factor"]),
            "method": proj["method"],
        }

    duration_h = float(storm_duration_h)
    sim_hours = float(solver_hours or duration_h)
    cfg = SolverConfig(dx=float(dx), dy=float(dy))
    scenario_depths: dict[int, np.ndarray] = {}

    for T in return_periods:
        total_mm = design_mm_day[int(T)]
        event_mm = total_mm * (duration_h / 24.0)
        hyeto = design_storm_hyetograph_mm_h(
            event_mm, duration_h=duration_h, n_steps=max(12, int(duration_h))
        )

        def rain_fn(t, hyeto=hyeto):
            idx = int(np.clip(t / 3600.0, 0, len(hyeto) - 1))
            return float(hyeto[idx])

        river_q = None
        if (river_mask is not None or river_path is not None) and river_peak_m3s > 0:
            ts = np.array([0.0, duration_h * 1800.0, duration_h * 3600.0])
            qs = np.array([0.0, float(river_peak_m3s), 0.0])
            river_q = Hydrograph(times_s=ts, discharge_m3s=qs)

        # Default coastal series: constant if scalar provided
        level_series = coastal_level_series
        if level_series is not None and np.isscalar(level_series):
            level = float(level_series)
            level_series = lambda t, level=level: level  # noqa: E731

        forcing = build_forcing_from_layers(
            dem=dem,
            dx=dx,
            dy=dy,
            rain_mm_per_hour=rain_fn,
            cn_map=cn if isinstance(cn, np.ndarray) else None,
            river_mask=river_mask,
            river_path=river_path,
            river_hydrograph=river_q,
            transform=transform,
            coastal_mask=coastal_mask,
            coastal_level_series=level_series,
            coastal_dt_s=coastal_dt_s,
            curve_number=float(cn) if np.isscalar(cn) else 75.0,
        )

        solver = ShallowWater2D(dem, config=cfg, manning=manning)
        logger.info("SWE T=%s event=%.1f mm", T, event_mm)
        solver.run(duration_s=sim_hours * 3600.0, forcing=forcing)
        h_max = solver.state.h_max if solver.state.h_max is not None else solver.state.h
        scenario_depths[int(T)] = np.where(np.isfinite(h_max), np.maximum(h_max, 0.0), 0.0)

    depth_maps = depth_return_period_from_scenario_depths(scenario_depths, return_periods)

    geotiff_paths: list[Path] = []
    if export_geotiff and output_dir is not None:
        geotiff_paths = export_depth_geotiffs(
            depth_maps, output_dir, transform=transform, crs=crs
        )

    return {
        "depth_maps_m": depth_maps,
        "design_rain_mm_day": design_mm_day,
        "precip_return_maps": rp_rain,
        "climate": climate_meta,
        "return_periods": list(return_periods),
        "geotiff_paths": [str(p) for p in geotiff_paths],
        "dx": dx,
        "dy": dy,
        "unit_depth": "m",
    }
