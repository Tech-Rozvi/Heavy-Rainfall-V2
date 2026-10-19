"""
Framework-free handlers for ROZVI scientific API (Phase 9).

Used by FastAPI routes when available, and by unit tests without FastAPI.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from src.rozvi import __eprf_version__, __platform_name__, __version__


def info() -> dict[str, Any]:
    return {
        "platform": __platform_name__,
        "version": __version__,
        "eprf_version": __eprf_version__,
        "scientific_claims": "docs/SCIENTIFIC_CLAIMS.md",
        "capability_matrix": "docs/CAPABILITY_MATRIX.md",
        "notes": [
            "Rainfall products are not flood depths.",
            "Depth products require an explicit hydraulics run and remain provisional until event-validated.",
            "Overall chain confidence is the weakest stage.",
        ],
    }


def capabilities() -> dict[str, Any]:
    return {
        "version": __version__,
        "capabilities": {
            "aoi_point": "IMPLEMENTED",
            "gev_return_periods": "IMPLEMENTED",
            "design_storm": "IMPLEMENTED",
            "event_hydrology": "IMPLEMENTED",
            "flood_depth": "PROVISIONAL",
            "financial_loss": "NOT_YET_IMPLEMENTED",
            "chain_uncertainty": "IMPLEMENTED",
            "nonstationary_evt": "NOT_YET_IMPLEMENTED",
            "event_validated_flood_maps": "NOT_YET_IMPLEMENTED",
        },
    }


def compute_return_periods(
    annual_maxima_mm: Sequence[float],
    *,
    return_periods: Sequence[int] = (10, 50, 100),
    n_bootstrap: int = 80,
    ci_level: float = 0.9,
) -> dict[str, Any]:
    from src.eprf.extremes.return_period_report import report_return_periods_1d

    am = np.asarray(annual_maxima_mm, dtype="float64")
    am = am[np.isfinite(am)]
    if len(am) < 5:
        raise ValueError("Need at least 5 finite annual maxima")
    results = report_return_periods_1d(
        am,
        return_periods=list(return_periods),
        n_bootstrap=int(n_bootstrap),
        ci=float(ci_level),
    )
    return {
        "n_years": int(len(am)),
        "results": [r.to_dict() for r in results],
        "disclaimer": (
            "Statistical return levels only. Extrapolation is flagged per result. "
            "Not a flood depth product."
        ),
    }


def compute_event_hydrology(
    hyetograph_mm: Sequence[float],
    *,
    area_km2: float,
    curve_number: float = 75.0,
    dt_h: float = 1.0,
    loss_method: str = "curve_number",
) -> dict[str, Any]:
    from src.hydrology import run_event_hydrology, LossMethod

    method = loss_method.lower()
    if method not in ("curve_number", "none"):
        raise ValueError("loss_method must be curve_number or none")
    loss = LossMethod.CURVE_NUMBER if method == "curve_number" else LossMethod.NONE
    result = run_event_hydrology(
        np.asarray(hyetograph_mm, dtype="float64"),
        area_km2=float(area_km2),
        loss_method=loss,
        curve_number=float(curve_number),
        dt_h=float(dt_h),
    )
    return {
        "peak_m3s": result.peak_m3s,
        "excess_total_mm": result.excess_total_mm,
        "precip_total_mm": result.precip_total_mm,
        "method_loss": result.method_loss,
        "method_routing": result.method_routing,
        "forcing": result.to_hydraulic_forcing_series(),
        "disclaimer": (
            "Event hydrology peak is not flood depth. CN/UH are not regionally "
            "calibrated in this repository."
        ),
    }


def compute_chain(stages: Sequence[dict[str, Any]]) -> dict[str, Any]:
    from src.rozvi.chain import StageUncertainty, build_chain, provenance_for_chain

    if not stages:
        raise ValueError("stages must be non-empty")
    objs = [
        StageUncertainty(
            stage=str(s["stage"]),
            confidence=str(s["confidence"]),
            quantified=bool(s.get("quantified", False)),
            estimate=s.get("estimate"),
            interval_low=s.get("interval_low"),
            interval_high=s.get("interval_high"),
            validation_status=str(s.get("validation_status", "not_validated")),
        )
        for s in stages
    ]
    chain = build_chain(objs)
    prov = provenance_for_chain(chain, aoi_id="api_request", product="chain_api")
    return {
        "chain": chain.to_dict(),
        "provenance": prov.to_dict(),
        "disclaimer": (
            "Overall confidence is the weakest stage, not a joint probability. "
            "Intervals apply only to stages that computed them."
        ),
    }
