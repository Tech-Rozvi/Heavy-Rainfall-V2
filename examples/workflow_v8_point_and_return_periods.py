#!/usr/bin/env python3
"""
Example end-to-end workflow (v8):
1. Define a point AOI (Harare) with 25 km buffer
2. Run AOI diagnostics
3. Compute return periods from synthetic annual maxima (stand-in for real series)
4. Generate a design storm for the 100-year level
5. Emit RainfallForcing for the hydraulics module
6. Apply a transparent climate delta (SSP245 mid-century)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eprf import point_to_aoi, PointMode, aoi_diagnostic_report
from src.eprf.extremes.return_period_report import (
    report_return_periods_1d,
    format_return_period_table,
)
from src.eprf.design_storm import generate_design_storm, TemporalPattern
from src.eprf.interfaces.contracts import ModuleOutputMeta, RainfallForcing
from src.eprf.climate_v2.delta import apply_delta_change, DeltaMethod


def main():
    # 1–2. AOI
    aoi = point_to_aoi(31.05, -17.83, crs="EPSG:4326", mode=PointMode.BUFFER, buffer_km=25)
    diag = aoi_diagnostic_report(aoi, station_count_nearby=2)
    print("=== AOI diagnostic ===")
    print(json.dumps(diag, indent=2, default=str))

    # 3. Return periods (synthetic 30-year AMS as demonstration)
    rng = np.random.default_rng(42)
    am = rng.gumbel(loc=45, scale=12, size=30)
    results = report_return_periods_1d(am, return_periods=[10, 50, 100, 500], n_bootstrap=80)
    print("\n=== Return periods ===")
    print(format_return_period_table(results))

    # 4–5. Design storm + forcing contract for T=100
    r100 = next(r for r in results if r.return_period_years == 100)
    storm = generate_design_storm(
        return_level_mm=r100.estimate_mm,
        return_period_years=100,
        duration_hours=24,
        temporal_pattern=TemporalPattern.ALTERNATING_BLOCK,
        confidence=r100.confidence,
        notes=[r100.confidence_rationale],
        metadata={"aoi_id": aoi.aoi_id},
    )
    meta = ModuleOutputMeta(
        aoi_id=aoi.aoi_id,
        module="eprf.design_storm",
        data_kind="estimated",
        return_period_years=100,
        confidence=r100.confidence,
        notes=storm.notes,
    )
    forcing = RainfallForcing(
        meta=meta,
        total_depth_mm=storm.total_depth_mm,
        duration_hours=storm.duration_hours,
        peak_intensity_mm_h=storm.peak_intensity_mm_h,
        hyetograph_mm=storm.hyetograph_mm,
        timestep_hours=storm.timestep_hours,
        temporal_pattern=storm.temporal_pattern,
    )
    print("\n=== RainfallForcing (for hydraulics) ===")
    print(json.dumps(forcing.to_dict(), indent=2, default=str)[:800], "...")

    # 6. Climate delta
    hist_rl = np.array([r.estimate_mm for r in results])
    adj, climate = apply_delta_change(
        hist_rl,
        delta=0.12,
        method=DeltaMethod.RELATIVE,
        aoi_id=aoi.aoi_id,
        ssp="ssp245",
        horizon_year=2050,
        is_extreme=True,
    )
    print("\n=== Climate-adjusted return levels (relative +12 %) ===")
    print("Historical:", hist_rl)
    print("Adjusted:  ", adj)
    print("Method:    ", climate.method, "| dynamical downscaling?", climate.is_dynamical_downscaling)

    out = ROOT / "outputs" / "eprf_v8_example"
    out.mkdir(parents=True, exist_ok=True)
    (out / "aoi_diagnostic.json").write_text(json.dumps(diag, indent=2, default=str))
    (out / "return_periods.json").write_text(
        json.dumps([r.to_dict() for r in results], indent=2)
    )
    (out / "rainfall_forcing.json").write_text(json.dumps(forcing.to_dict(), indent=2, default=str))
    (out / "climate_adjustment.json").write_text(json.dumps(climate.to_dict(), indent=2, default=str))
    print(f"\nOutputs written to {out}")


if __name__ == "__main__":
    main()
