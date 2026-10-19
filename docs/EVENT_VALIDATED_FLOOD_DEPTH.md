# Event-validated flood depths

**ROZVI ≥ 0.11**

## Principle

Depth GeoTIFFs stay **`provisional`** until an **event validation report** passes
user-defined criteria against **real observations**.

`event_validated` applies to **that event’s depth field**, not automatically to
design return-period maps or other events.

## Required inputs

1. Simulated depth grid for a **named flood event** (hydraulics + event rainfall)
2. **High-water marks** CSV: `x,y,depth_m[,mark_id,source,notes]`
3. Optional binary **observed inundation** raster (same grid) for CSI/F1

## API

```python
from src.hydraulics import (
    evaluate_event_depth, HighWaterMark,
    load_high_water_marks_csv, save_validation_report,
    apply_validation_to_labels,
)
from src.hydraulics.pipeline import export_depth_geotiffs

marks = load_high_water_marks_csv("data/events/harare_2019_hwm.csv")
report = evaluate_event_depth(
    depth_m, marks,
    event_id="harare_2019_jan",
    transform=transform,   # or bounds=
    min_marks=3,
    max_mae_m=0.30,
    max_abs_bias_m=0.30,
    # observed_wet=footprint, min_csi=0.5,  # optional
)
save_validation_report(report, "outputs/validation/harare_2019.json")
export_depth_geotiffs(
    {"depth_event_hmax_m": depth_m},
    "outputs/validation",
    transform=transform,
    validation_status=report.validation_status,
    event_id=report.event_id,
)
```

## Default pass criteria

| Criterion | Default |
|-----------|---------|
| Min compared HWM | 3 |
| Max MAE | 0.30 m |
| Max \|bias\| | 0.30 m |
| Min CSI | off unless set |

Tighten criteria for stricter validation; document them **before** evaluating.

## Not claimed

- Regulatory / building-code design flood approval
- Automatic validation of T-year design maps
- Financial loss accuracy

## Demo

```bash
PYTHONPATH=. python examples/workflow_event_validation.py
```
