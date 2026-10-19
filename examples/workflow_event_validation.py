#!/usr/bin/env python3
"""
Demonstrate event depth validation against high-water marks (synthetic demo).

Replace the synthetic depth and marks with:
  - depth from a real hydraulic run for a named flood event
  - surveyed / reported high-water marks for that event

event_validated is set only when pass criteria are met.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.hydraulics.validate_depth import (
    HighWaterMark,
    evaluate_event_depth,
    apply_validation_to_labels,
)
from src.hydraulics.event_catalogue import save_validation_report
from src.hydraulics.pipeline import export_depth_geotiffs


def main() -> int:
    out = ROOT / "outputs" / "event_validation_demo"
    out.mkdir(parents=True, exist_ok=True)

    # Synthetic basin: deeper in centre
    n = 40
    y, x = np.mgrid[0:n, 0:n]
    depth = np.maximum(0.0, 1.2 - 0.002 * ((x - 20) ** 2 + (y - 20) ** 2))

    # Synthetic HWMs near the field (grid indices as x,y for demo)
    marks = [
        HighWaterMark(x=20, y=20, depth_m=1.15, mark_id="hwm_centre", source="demo"),
        HighWaterMark(x=15, y=18, depth_m=0.95, mark_id="hwm_a", source="demo"),
        HighWaterMark(x=25, y=22, depth_m=0.90, mark_id="hwm_b", source="demo"),
        HighWaterMark(x=10, y=10, depth_m=0.35, mark_id="hwm_edge", source="demo"),
    ]

    report = evaluate_event_depth(
        depth,
        marks,
        event_id="demo_synthetic_event",
        min_marks=3,
        max_mae_m=0.30,
        max_abs_bias_m=0.30,
    )
    labels = apply_validation_to_labels(depth, report)
    save_validation_report(report, out / "validation_report.json")

    paths = []
    try:
        from rasterio.transform import from_bounds
        transform = from_bounds(0, 0, n, n, n, n)
        paths = export_depth_geotiffs(
            {"depth_event_hmax_m": depth},
            out,
            transform=transform,
            validation_status=report.validation_status,
            event_id=report.event_id,
        )
    except Exception as exc:
        print(f"GeoTIFF export skipped: {exc}")

    summary = {
        "validation_status": report.validation_status,
        "passed": report.passed,
        "metrics": report.point_metrics,
        "labels": labels,
        "geotiffs": [str(p) for p in paths],
        "notes": report.notes,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
