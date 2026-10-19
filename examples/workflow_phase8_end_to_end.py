#!/usr/bin/env python3
"""
Phase 8 end-to-end demonstration (scientifically honest).

Chain:
  point AOI → synthetic AMS → return periods → design storm → RainfallForcing
  → event hydrology → optional hydraulic smoke run → asset query → chain uncertainty

This script uses synthetic annual maxima and a toy DEM.  It demonstrates
interfaces and uncertainty labels — not operational skill for a real city.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eprf.aoi.ingest import AOIRecord
from src.eprf import aoi_diagnostic_report
try:
    from src.eprf import point_to_aoi, PointMode
except Exception:  # pragma: no cover
    point_to_aoi = None  # type: ignore
    PointMode = None  # type: ignore
from src.eprf.extremes.return_period_report import (
    report_return_periods_1d,
    format_return_period_table,
)
from src.eprf.design_storm import generate_design_storm
from src.eprf.interfaces.contracts import ModuleOutputMeta, RainfallForcing
from src.eprf.interfaces.hydraulics_bridge import (
    rainfall_forcing_to_hydraulic_run,
    label_depth_product,
)
from src.hydrology import run_event_hydrology, LossMethod
from src.risk import assets_from_coordinates, query_assets_hazard, build_risk_snapshot
from src.rozvi.chain import (
    build_chain,
    stage_from_return_period,
    stage_from_hydrology,
    stage_from_hydraulics,
    stage_from_exposure,
    provenance_for_chain,
)


def main() -> int:
    out_dir = ROOT / "outputs" / "phase8_demo"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. AOI (prefer full AOI stack; fall back without geopandas)
    if point_to_aoi is not None:
        try:
            aoi = point_to_aoi(31.05, -17.83, crs="EPSG:4326", mode=PointMode.BUFFER, buffer_km=10)
        except Exception:
            aoi = None
    else:
        aoi = None
    if aoi is None:
        # Minimal AOIRecord for demo environments lacking geopandas
        lon, lat, buf = 31.05, -17.83, 0.1
        aoi = AOIRecord(
            aoi_id="demo_point_harare",
            geometry_type="BBox",
            crs="EPSG:4326",
            original_crs="EPSG:4326",
            crs_confidence="user_supplied",
            bounds=(lon - buf, lat - buf, lon + buf, lat + buf),
            area_km2=None,
            n_features=1,
            geojson={"type": "Point", "coordinates": [lon, lat]},
            analysis_mask_bounds=(lon - buf, lat - buf, lon + buf, lat + buf),
            point_mode="buffer",
            buffer_radius_km=10.0,
            user_coordinate=(lon, lat),
            user_crs="EPSG:4326",
            warnings=["AOI constructed without geopandas (demo fallback)."],
        )
    try:
        diag = aoi_diagnostic_report(aoi)
    except Exception as exc:
        diag = {"status": "warning", "message": str(exc)}
    print("=== AOI ===")
    print(json.dumps({"aoi_id": aoi.aoi_id, "bounds": aoi.bounds, "diag": diag}, indent=2, default=str))

    # 2. Return periods (synthetic AMS — demonstration only)
    rng = np.random.default_rng(42)
    am = rng.gumbel(loc=45.0, scale=12.0, size=25)
    rp_results = report_return_periods_1d(am, return_periods=[10, 50, 100], n_bootstrap=60)
    print("\n=== Return periods (synthetic AMS) ===")
    print(format_return_period_table(rp_results))
    r100 = next(r for r in rp_results if r.return_period_years == 100)

    # 3. Design storm + RainfallForcing
    storm = generate_design_storm(
        return_level_mm=r100.estimate_mm,
        return_period_years=100,
        duration_hours=6.0,
        timestep_hours=1.0,
    )
    hyeto = list(np.asarray(storm.hyetograph_mm, dtype=float).ravel())
    forcing = RainfallForcing(
        meta=ModuleOutputMeta(
            aoi_id=aoi.aoi_id,
            module="eprf_design_storm",
            data_kind="estimated",
            return_period_years=100,
            confidence=r100.confidence,
        ),
        total_depth_mm=float(np.sum(hyeto)),
        duration_hours=6.0,
        peak_intensity_mm_h=float(max(hyeto)) if hyeto else 0.0,
        hyetograph_mm=hyeto,
        timestep_hours=1.0,
        temporal_pattern=str(getattr(storm, "pattern", "design")),
    )
    forcing.assert_not_flood_depth()

    # 4. Event hydrology
    hydro = run_event_hydrology(
        np.asarray(hyeto),
        area_km2=25.0,
        loss_method=LossMethod.CURVE_NUMBER,
        curve_number=80.0,
        dt_h=1.0,
    )
    print(f"\n=== Hydrology === peak={hydro.peak_m3s:.3f} m³/s  excess={hydro.excess_total_mm:.1f} mm")

    # 5. Optional hydraulics on toy DEM (provisional)
    n = 12
    y, x = np.mgrid[0:n, 0:n]
    dem = 10.0 + 0.04 * ((x - n / 2) ** 2 + (y - n / 2) ** 2)
    hyd_result = rainfall_forcing_to_hydraulic_run(
        forcing,
        dem,
        bounds=(0.0, 0.0, n * 30.0, n * 30.0),
        dx=30.0,
        dy=30.0,
        run_solver=True,
        duration_s=1200.0,
        manning_n=0.05,
    )
    depth_meta = None
    max_depth = None
    if hyd_result.max_depth_m is not None:
        depth_meta = label_depth_product(np.asarray(hyd_result.max_depth_m))
        max_depth = float(np.nanmax(hyd_result.max_depth_m))
        print(f"=== Hydraulics (PROVISIONAL) === max_depth={max_depth:.3f} m  status={hyd_result.validation_status}")

    # 6. Asset query on depth field (or zeros if no depth)
    field = np.asarray(hyd_result.max_depth_m) if hyd_result.max_depth_m is not None else np.zeros((n, n))
    assets = assets_from_coordinates([(3, 3), (6, 6), (9, 9)], asset_type="address")
    asset_results = query_assets_hazard(
        assets, {"flood_depth_m": field}, hazard_validation_status="provisional"
    )
    snap = build_risk_snapshot(
        aoi.aoi_id,
        hazard_layers={"flood_depth_m": field},
        hazard_validation_status="provisional",
        asset_results=asset_results,
    )

    # 7. Chain uncertainty + provenance
    chain = build_chain([
        stage_from_return_period(r100),
        stage_from_hydrology(
            method="curve_number",
            peak_m3s=hydro.peak_m3s,
            sensitivity_peaks_m3s=[
                hydro.peak_m3s * 0.8,
                hydro.peak_m3s,
                hydro.peak_m3s * 1.3,
            ] if hydro.peak_m3s else None,
        ),
        stage_from_hydraulics(
            validation_status=hyd_result.validation_status,
            max_depth_m=max_depth,
        ),
        stage_from_exposure(hazard_validation_status="provisional"),
    ])
    prov = provenance_for_chain(chain, aoi_id=aoi.aoi_id, product="phase8_demo")

    summary = {
        "aoi_id": aoi.aoi_id,
        "return_level_100y_mm": r100.estimate_mm,
        "return_confidence": r100.confidence,
        "hydro_peak_m3s": hydro.peak_m3s,
        "hydraulics_validation_status": hyd_result.validation_status,
        "depth_product": depth_meta,
        "risk_disclaimers": snap.disclaimers,
        "chain": chain.to_dict(),
        "provenance": prov.to_dict(),
        "scientific_note": (
            "Demonstration with synthetic AMS and toy DEM. "
            "Not an operational or regulatory flood assessment."
        ),
    }
    path = out_dir / "summary.json"
    path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n=== Chain confidence: {chain.overall_confidence} (weakest: {chain.weakest_stage}) ===")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
