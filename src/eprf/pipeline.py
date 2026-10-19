"""
EPRF v7.0 end-to-end pipeline.

Produces:
1. ETCCDI diagnostic indices (historical characterisation)
2. GEV return levels + bootstrap CIs for standard return periods
3. Data-quality / confidence flags
4. Optional susceptibility diagnostic (non-circular predictors only)
5. Validation report against independent observations when available
6. Full provenance metadata
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from src.utils import get_logger, load_config
from src.eprf.features.indices import compute_etccdi_indices
from src.eprf.extremes.gev import annual_maxima_series, return_levels_with_ci, STANDARD_RETURN_PERIODS
from src.eprf.uncertainty.quality import data_quality_flags, CONFIDENCE_LABELS
from src.eprf.validation.metrics import evaluate_precipitation, evaluate_extremes

logger = get_logger("eprf.pipeline")


def run_eprf(
    daily_precip: np.ndarray,
    config: dict,
    output_dir: Optional[Path] = None,
    station_obs: Optional[dict] = None,
    extra_layers: Optional[dict[str, np.ndarray]] = None,
) -> dict[str, Any]:
    """
    Core EPRF analysis on a daily precipitation cube.

    Parameters
    ----------
    daily_precip : (T, Y, X) array, mm/day
    config : loaded eprf_config.yaml
    output_dir : where to write NetCDF/GeoTIFF/JSON
    station_obs : optional dict with 'values', 'rows', 'cols' for validation
    extra_layers : optional predictor rasters (for susceptibility diagnostic)
    """
    cfg = config
    out_dir = Path(output_dir or cfg.get("paths", {}).get("output_dir", "outputs/eprf"))
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = datetime.now(timezone.utc)
    logger.info("EPRF v7.0 pipeline start — shape %s", daily_precip.shape)

    # ------------------------------------------------------------------
    # 1. ETCCDI indices (diagnostic characterisation, not predictors)
    # ------------------------------------------------------------------
    indices = compute_etccdi_indices(daily_precip)
    logger.info("ETCCDI indices computed: %s", list(indices.keys()))

    # ------------------------------------------------------------------
    # 2. Annual maxima + GEV return levels with bootstrap CI
    # ------------------------------------------------------------------
    extremes_cfg = cfg.get("extremes", {})
    rps = extremes_cfg.get("return_periods", list(STANDARD_RETURN_PERIODS))
    n_boot = int(extremes_cfg.get("n_bootstrap", 200))
    ci = float(extremes_cfg.get("ci_level", 0.90))

    am = annual_maxima_series(daily_precip)
    logger.info("Annual maxima series: %s", am.shape)

    rl = return_levels_with_ci(
        am,
        return_periods=rps,
        n_bootstrap=n_boot,
        ci=ci,
        random_seed=int(cfg.get("project", {}).get("random_seed", 42)),
    )
    logger.info("Return levels computed for T = %s", rps)

    # ------------------------------------------------------------------
    # 3. Quality / confidence flags
    # ------------------------------------------------------------------
    qcfg = cfg.get("uncertainty", {})
    flags = data_quality_flags(
        rl["n_years"],
        min_years_high=qcfg.get("quality_min_years_high", 20),
        min_years_moderate=qcfg.get("quality_min_years_moderate", 10),
        min_years_low=qcfg.get("quality_min_years_low", 5),
    )

    # ------------------------------------------------------------------
    # 4. Optional validation against point observations
    # ------------------------------------------------------------------
    validation = {}
    if station_obs is not None:
        try:
            # Simple nearest-pixel extraction for MAP / Rx1day
            rows = station_obs["rows"]
            cols = station_obs["cols"]
            obs_vals = station_obs["values"]
            sim_map = indices["map_mm"][rows, cols]
            validation["map"] = evaluate_precipitation(obs_vals, sim_map)
            logger.info("Validation (MAP): %s", validation["map"])
        except Exception as exc:
            logger.warning("Station validation failed: %s", exc)
            validation["error"] = str(exc)

    # ------------------------------------------------------------------
    # 5. Provenance
    # ------------------------------------------------------------------
    provenance = {
        "model_name": "EPRF",
        "version": cfg.get("project", {}).get("version", "7.0.0"),
        "timestamp_utc": t0.isoformat(),
        "input_shape": list(daily_precip.shape),
        "n_years_annual_maxima": int(am.shape[0]),
        "return_periods": list(rps),
        "n_bootstrap": n_boot,
        "ci_level": ci,
        "random_seed": cfg.get("project", {}).get("random_seed", 42),
        "scientific_claims": [
            "ETCCDI indices are diagnostic characterisations of the historical record.",
            "Return levels are GEV quantiles fitted to annual maxima with parametric bootstrap CIs.",
            "Pixel-wise fits assume spatial independence of extremes.",
            "This is not a numerical weather prediction system.",
        ],
        "limitations": [
            "Record length limits reliable high return periods.",
            "No dynamical downscaling; climate projections use transparent delta-change.",
            "Spatial coherence of extremes is not modelled.",
        ],
    }

    # ------------------------------------------------------------------
    # 6. Persist key outputs
    # ------------------------------------------------------------------
    np.savez_compressed(
        out_dir / "eprf_indices.npz",
        **{k: v for k, v in indices.items() if isinstance(v, np.ndarray)},
    )
    np.savez_compressed(
        out_dir / "eprf_return_levels.npz",
        **{k: v for k, v in rl.items() if isinstance(v, np.ndarray)},
    )
    np.save(out_dir / "eprf_confidence_flags.npy", flags)

    with open(out_dir / "provenance.json", "w") as f:
        json.dump(provenance, f, indent=2)
    with open(out_dir / "validation.json", "w") as f:
        json.dump(validation, f, indent=2, default=str)

    def _safe_nanmean(a) -> float:
        arr = np.asarray(a, dtype="float64")
        if arr.size == 0 or not np.isfinite(arr).any():
            return float("nan")
        with np.errstate(all="ignore"):
            return float(np.nanmean(arr))

    n_years_ams = None
    try:
        # annual maxima cube is (n_years, y, x) when produced upstream
        am = provenance.get("n_years") or validation.get("n_years")
        n_years_ams = am
    except Exception:
        pass

    # Summary statistics for the report
    summary = {
        "map_mm_mean": _safe_nanmean(indices["map_mm"]),
        "rx1day_mean": _safe_nanmean(indices["rx1day"]),
        "rl_100_mean": _safe_nanmean(rl.get("rl_100", np.array([np.nan]))),
        "rl_100_mean_lower": _safe_nanmean(rl.get("rl_100_lower", np.array([np.nan]))),
        "rl_100_mean_upper": _safe_nanmean(rl.get("rl_100_upper", np.array([np.nan]))),
        "confidence_counts": {
            CONFIDENCE_LABELS[k]: int(np.sum(flags == k)) for k in CONFIDENCE_LABELS
        },
        "validation": validation,
        "provenance": provenance,
        "notes": [],
    }
    if summary["rl_100_mean"] != summary["rl_100_mean"]:  # NaN
        summary["notes"].append(
            "100-year return levels are undefined/NaN: typically the annual-maxima "
            "record is too short for a stable GEV fit (need preferably ≥20–30 years). "
            "Use a longer CHIRPS series (e.g. 1981–2023)."
        )
    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    logger.info("EPRF pipeline complete. Outputs written to %s", out_dir)
    return {
        "indices": indices,
        "return_levels": rl,
        "confidence_flags": flags,
        "validation": validation,
        "summary": summary,
        "output_dir": str(out_dir),
    }
