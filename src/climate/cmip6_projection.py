"""
cmip6_projection.py — Ensemble CMIP6 delta-change tables & spatial scales.

Supports:
* Multi-GCM JSON/CSV tables (EC-Earth3, MPI-ESM1-2-HR, … × SSP × horizon)
* Ensemble mean / median / percentile aggregation
* Pixel-wise ΔP/P_hist rasters for spatially varying future scaling
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

SSP_SCENARIOS = ("ssp126", "ssp245", "ssp370", "ssp585")

_DEFAULT_DELTA_PCT: dict[tuple[str, int], float] = {
    ("ssp126", 2030): 3.0, ("ssp126", 2050): 5.0, ("ssp126", 2080): 7.0,
    ("ssp245", 2030): 5.0, ("ssp245", 2050): 9.0, ("ssp245", 2080): 14.0,
    ("ssp370", 2030): 6.0, ("ssp370", 2050): 12.0, ("ssp370", 2080): 20.0,
    ("ssp585", 2030): 7.0, ("ssp585", 2050): 15.0, ("ssp585", 2080): 28.0,
}


@dataclass(frozen=True)
class ClimateHorizon:
    ssp: str = "ssp245"
    horizon_year: int = 2050
    hist_start: int = 1995
    hist_end: int = 2014
    fut_window_years: int = 20

    def __post_init__(self):
        ssp = self.ssp.lower().replace("-", "").replace(".", "")
        if not ssp.startswith("ssp"):
            ssp = "ssp" + ssp
        object.__setattr__(self, "ssp", ssp)


def _norm_ssp(s: str) -> str:
    s = str(s).lower().replace("-", "").replace(".", "").replace("_", "")
    if s.startswith("ssp"):
        return s
    return "ssp" + s


def load_cmip6_delta_table(
    path: str | Path,
    *,
    ensemble_stat: str = "mean",
) -> dict[tuple[str, int], float]:
    """
    Ingest regional CMIP6 ensemble deltas (% change in extreme precip).

    Accepted JSON layouts
    ---------------------
    A) Simple::
        {"ssp245": {"2030": 5.0, "2050": 9.0}}

    B) Multi-GCM::
        {
          "ssp245": {
            "2050": {
              "EC-Earth3": 8.1,
              "MPI-ESM1-2-HR": 10.2,
              "ACCESS-CM2": 7.5
            }
          }
        }
      → aggregated with ``ensemble_stat`` ∈ {mean, median, p10, p90}.

    CSV columns (flexible names)
    ----------------------------
    ssp, horizon_year, delta_pct [, gcm]
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    table: dict[tuple[str, int], float] = {}

    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text())
        for ssp_key, horizons in raw.items():
            ssp = _norm_ssp(ssp_key)
            for y_key, val in horizons.items():
                year = int(y_key)
                if isinstance(val, dict):
                    # multi-GCM
                    vals = np.array([float(v) for v in val.values()], dtype="float64")
                    table[(ssp, year)] = float(_ensemble_reduce(vals, ensemble_stat))
                else:
                    table[(ssp, year)] = float(val)
    else:
        with path.open(newline="") as f:
            reader = csv.DictReader(f)
            # group by (ssp, year) if multiple GCMs
            buckets: dict[tuple[str, int], list[float]] = {}
            for row in reader:
                # flexible headers
                ssp = _norm_ssp(row.get("ssp") or row.get("scenario") or row.get("SSP"))
                year = int(row.get("horizon_year") or row.get("year") or row.get("horizon"))
                delta = float(row.get("delta_pct") or row.get("delta") or row.get("change_pct"))
                buckets.setdefault((ssp, year), []).append(delta)
            for key, vals in buckets.items():
                table[key] = float(_ensemble_reduce(np.asarray(vals), ensemble_stat))

    logger.info(
        "Loaded CMIP6 delta table (%d entries, ensemble=%s) from %s",
        len(table), ensemble_stat, path,
    )
    return table


def _ensemble_reduce(vals: np.ndarray, stat: str) -> float:
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return 0.0
    stat = stat.lower()
    if stat == "median":
        return float(np.median(vals))
    if stat == "p10":
        return float(np.percentile(vals, 10))
    if stat == "p90":
        return float(np.percentile(vals, 90))
    return float(np.mean(vals))


def load_spatial_delta_raster(
    path: str | Path,
    *,
    band: int = 1,
) -> np.ndarray:
    """Load a GeoTIFF of ΔP/P_hist in **percent** (pixel-wise climate change)."""
    import rasterio

    with rasterio.open(path) as src:
        arr = src.read(band).astype("float64")
        nodata = src.nodata
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)
    return arr


def delta_change_scale(
    horizon: ClimateHorizon,
    *,
    delta_table: Optional[Mapping[tuple[str, int], float]] = None,
    spatial_delta_pct: Optional[np.ndarray] = None,
    allow_default_factors: bool = False,
) -> float | np.ndarray:
    """
    Multiplicative scale s = 1 + ΔP/P_hist.

    Prefer ``spatial_delta_pct`` (2-D %) when available; else scalar from table.
    """
    if spatial_delta_pct is not None:
        d = np.asarray(spatial_delta_pct, dtype="float64")
        return 1.0 + np.where(np.isfinite(d), d, 0.0) / 100.0

    table = dict(delta_table) if delta_table is not None else {}
    key = (horizon.ssp, int(horizon.horizon_year))
    if key in table:
        delta_pct = float(table[key])
    else:
        candidates = [(y, v) for (s, y), v in table.items() if s == horizon.ssp]
        if candidates:
            y_near, val = min(candidates, key=lambda t: abs(t[0] - horizon.horizon_year))
            logger.warning("Using nearest horizon %s for %s", y_near, key)
            delta_pct = val
        elif allow_default_factors and key in _DEFAULT_DELTA_PCT:
            delta_pct = _DEFAULT_DELTA_PCT[key]
            logger.warning("PLACEHOLDER default ΔP=%.1f%% for %s", delta_pct, key)
        elif allow_default_factors:
            delta_pct = _DEFAULT_DELTA_PCT.get((horizon.ssp, 2050), 10.0)
            logger.warning("PLACEHOLDER generic ΔP=%.1f%% for %s", delta_pct, key)
        else:
            raise KeyError(
                f"No CMIP6 delta for {key}. Pass delta_table or spatial_delta_pct."
            )
    return 1.0 + float(delta_pct) / 100.0


def scale_return_levels(
    baseline_levels: Mapping[str, float | np.ndarray],
    scale: float | np.ndarray,
) -> dict[str, float | np.ndarray]:
    out: dict[str, float | np.ndarray] = {}
    for k, v in baseline_levels.items():
        if isinstance(v, str):
            continue
        arr = np.asarray(v, dtype="float64")
        scaled = arr * scale
        out[k] = float(scaled) if scaled.ndim == 0 else scaled
    return out


def project_design_storms(
    baseline_mm_day: Mapping[int, float],
    horizon: ClimateHorizon,
    *,
    delta_table: Optional[Mapping[tuple[str, int], float]] = None,
    spatial_delta_pct: Optional[np.ndarray] = None,
    allow_default_factors: bool = False,
    storm_duration_h: float = 24.0,
    return_periods: Sequence[int] = (10, 50, 100, 250, 500),
) -> dict[str, Any]:
    from src.statistics.evt_return_periods import design_storm_hyetograph_mm_h

    scale = delta_change_scale(
        horizon,
        delta_table=delta_table,
        spatial_delta_pct=spatial_delta_pct,
        allow_default_factors=allow_default_factors,
    )
    # If scale is spatial, use domain mean for scalar design storm driver
    scale_scalar = float(np.nanmean(scale)) if not np.isscalar(scale) else float(scale)

    future_mm_day: dict[int, float] = {}
    future_event_mm: dict[int, float] = {}
    hyetographs: dict[int, np.ndarray] = {}
    for T in return_periods:
        base = float(baseline_mm_day.get(int(T), baseline_mm_day.get(T, 0.0)))  # type: ignore
        fut = base * scale_scalar
        future_mm_day[int(T)] = fut
        event = fut * (storm_duration_h / 24.0)
        future_event_mm[int(T)] = event
        hyetographs[int(T)] = design_storm_hyetograph_mm_h(
            event, duration_h=storm_duration_h, n_steps=max(12, int(storm_duration_h))
        )
    return {
        "scale_factor": scale,
        "scale_factor_scalar": scale_scalar,
        "future_mm_day": future_mm_day,
        "future_event_mm": future_event_mm,
        "hyetographs_mm_h": hyetographs,
        "ssp": horizon.ssp,
        "horizon_year": horizon.horizon_year,
        "storm_duration_h": storm_duration_h,
        "method": "delta_change_cmip6_ensemble",
    }


def cmip6_delta_from_xarray(
    hist_precip: Any,
    fut_precip: Any,
    *,
    extreme_percentile: float = 95.0,
) -> np.ndarray:
    def _p95(a):
        a = np.asarray(a, dtype="float64")
        if a.ndim == 3:
            with np.errstate(all="ignore"):
                return np.nanpercentile(a, extreme_percentile, axis=0)
        return a

    h, f = _p95(hist_precip), _p95(fut_precip)
    return 100.0 * (f - h) / np.maximum(h, 1e-3)
