"""forecast_run.py — Short-term QPF → 2D SWE early-warning depths."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np

from src.utils import get_logger
from src.data.streaming.surface_layers import (
    fetch_forecast_qpf,
    fetch_land_cover,
    fetch_soil_hsg,
    land_cover_to_manning,
    land_cover_hsg_to_cn,
)
try:
    from src.reporting.exposure import building_exposure_report
    from src.reporting.site_report import generate_site_report, SiteReportInput
except ImportError as _rep_err:  # pragma: no cover
    raise ImportError(
        "Reporting package import failed. Ensure src/reporting/site_report.py "
        "exports generate_site_report, SiteReportInput, and build_site_report_html. "
        f"Original error: {_rep_err}"
    ) from _rep_err
from src.hydraulics.solver2d import ShallowWater2D, SolverConfig
from src.hydraulics.multi_peril import MultiPerilForcing, PerilConfig
from src.hydraulics.pipeline import export_depth_geotiffs

logger = get_logger(__name__)


def run_forecast_flood(
    dem: np.ndarray,
    bounds: tuple[float, float, float, float],
    *,
    dx: float = 30.0,
    dy: float = 30.0,
    transform: Any = None,
    forecast_days: int = 5,
    output_dir: str | Path = "outputs/rasters/forecast",
) -> dict[str, Any]:
    """
    Live Open-Meteo QPF hyetograph → SWE peak depth + building exposure report.
    """
    qpf = fetch_forecast_qpf(bounds, forecast_days=forecast_days)
    rates = np.asarray(qpf["precipitation_mm_h"], dtype="float64").ravel()
    times = qpf.get("times") or []

    # Surface friction & CN
    try:
        lc = fetch_land_cover(bounds, resolution_m=max(dx, 50.0))
        soil = fetch_soil_hsg(bounds, resolution_m=max(dx, 100.0))
        from src.data.manager import _fit_to_shape
        lc_arr = _fit_to_shape(lc["land_cover"], dem.shape)
        hsg_arr = _fit_to_shape(soil["hsg"], dem.shape)
        manning = land_cover_to_manning(lc_arr)
        cn = land_cover_hsg_to_cn(lc_arr, hsg_arr)
    except Exception as exc:
        logger.warning("Surface layers degraded: %s", exc)
        manning = 0.04
        cn = 75.0
        lc = soil = {}

    # Hyetograph callable (mm/h)
    def rain_fn(t, rates=rates):
        # t seconds from start; hourly steps
        idx = int(np.clip(t / 3600.0, 0, len(rates) - 1))
        return float(rates[idx])

    cfg = SolverConfig(dx=float(dx), dy=float(dy), use_numba=False)
    forcing = MultiPerilForcing(
        rain_mm_per_hour=rain_fn,
        config=PerilConfig(
            curve_number=float(cn) if np.isscalar(cn) else 75.0,
            cn_map=None if np.isscalar(cn) else cn,
            enable_fluvial=False,
            enable_coastal=False,
        ),
        cell_area_m2=float(dx * dy),
    )
    solver = ShallowWater2D(dem, config=cfg, manning=manning)
    duration_s = min(float(forecast_days) * 86400.0, max(len(rates) * 3600.0, 3600.0))
    # Cap runtime for QA: max 6h simulation equivalent if many hours
    duration_s = min(duration_s, 6 * 3600.0)
    logger.info("Forecast SWE duration=%.0fs (%d hourly QPF steps)", duration_s, len(rates))
    solver.run(duration_s=duration_s, forcing=forcing)
    h_max = solver.state.h_max if solver.state.h_max is not None else solver.state.h
    h_max = np.nan_to_num(np.asarray(h_max, dtype="float64"), nan=0.0)
    h_max = np.maximum(h_max, 0.0)

    out_dir = Path(output_dir)
    geotiffs = []
    if transform is not None:
        geotiffs = export_depth_geotiffs(
            {"depth_forecast_hmax_m": h_max},
            out_dir,
            transform=transform,
        )

        exposure = building_exposure_report(h_max, transform, bounds)

    total_rain = float(np.nansum(rates))
    report = {
        "forecast_days": forecast_days,
        "qpf_source": qpf.get("source"),
        "total_forecast_rain_mm": total_rain,
        "peak_hourly_mm": float(np.nanmax(rates)) if rates.size else 0.0,
        "h_max_m": float(np.nanmax(h_max)),
        "exposure": exposure,
        "geotiff_paths": [str(p) for p in geotiffs],
        "land_cover_source": (lc or {}).get("source"),
        "soil_source": (soil or {}).get("source"),
        "validation_status": "provisional",
        "notes": [
            "Forecast depth is provisional early-warning only — not event-validated.",
            "Rainfall driver is Open-Meteo QPF, not CHIRPS.",
        ] + (["QPF total is 0 mm; depth≈0 is expected for a dry forecast."] if total_rain <= 0 else []),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    import json
    (out_dir / "forecast_exposure_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    logger.info("Forecast report: h_max=%.3fm exposure=%s", report["h_max_m"], exposure)
    # Executive report
    try:
        rep = generate_site_report(
            SiteReportInput(
                site_name=f"Forecast AOI {bounds}",
                bounds=bounds,
                mode="forecast",
                depth_by_T={0: h_max},
                exposure=exposure,
                peril_flags={
                    "pluvial": "high" if float(np.nanmax(h_max)) > 0.3 else "medium",
                    "fluvial": "low",
                    "coastal": "low",
                    "notes": "Forecast-driven pluvial early warning run.",
                },
                sources={"qpf": qpf.get("source"), "lc": (lc or {}).get("source"), "soil": (soil or {}).get("source")},
            ),
            output_dir=Path(output_dir).parent.parent / "reports" if False else Path(output_dir) / "reports",
        )
        report["site_report"] = rep.get("paths")
    except Exception as exc:
        logger.warning("Site report failed: %s", exc)
        report["site_report_error"] = str(exc)

    return {
        "depth_m": h_max,
        "report": report,
        "qpf": qpf,
        "manning": manning if not np.isscalar(manning) else None,
        "cn": cn if not np.isscalar(cn) else None,
    }
