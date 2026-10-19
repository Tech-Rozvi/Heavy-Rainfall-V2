# Phase 5 — Hydraulics Validation & Product Labelling

**Date:** 2026-10-09  
**Platform:** ROZVI **0.4.0**  
**EPRF engine:** 8.2.0  

---

## Objectives

1. Keep the 2D SWE solver; add **smoke tests**  
2. Label depth / inundation products as **provisional** until event-validated  
3. Ensure **RainfallForcing** is the supported rainfall → hydraulics interface  

---

## Implemented

### Contract hardening (`src/eprf/interfaces/contracts.py`)

`HydraulicResult` now includes:

- `validation_status`: `provisional` | `event_validated` | `research_only` (default **provisional**)
- `validation_notes` with mandatory provisional disclaimer
- `product_labels` (`provisional_flood_depth`, `provisional_inundation_extent`)
- `is_provisional()` helper

### Bridge (`src/eprf/interfaces/hydraulics_bridge.py`)

- Preferred path: **direct** `ShallowWater2D` driven by `RainfallForcing` hyetograph (`_HyetographForcing`)
- `run_solver=False` dry-run: metadata only, **no fabricated depths**
- `label_depth_product()` for API/GIS metadata
- Fallback to `forecast_run` still marked provisional and notes hyetograph limitation

### GeoTIFF tags (`src/hydraulics/pipeline.py`)

Depth exports carry:

- `validation_status=provisional`
- `product_label=provisional_flood_depth`
- disclaimer text in tags

### Tests (`tests/hydraulics/test_solver_smoke.py`) — **6 passed**

| Test | Checks |
|------|--------|
| RainfallForcing guard | cannot carry `hydraulically_simulated` |
| Dry run | no depths when solver off |
| Direct solver smoke | toy DEM + design storm → non-zero depth, provisional flags |
| label_depth_product | metadata/disclaimer |
| Solver without forcing | stable short run |
| HydraulicResult default | provisional by default |

---

## Explicit non-claims

- Depth maps are **not** event-validated against observed floods in this repo  
- Not a regulatory flood hazard product  
- Smoke tests use a synthetic bowl DEM — not a regional calibration  
- Full multi-peril (fluvial/coastal) event validation is still open  

---

## Usage

```python
from src.eprf.interfaces import (
    RainfallForcing, ModuleOutputMeta,
    rainfall_forcing_to_hydraulic_run, label_depth_product,
)
import numpy as np

forcing = RainfallForcing(
    meta=ModuleOutputMeta(aoi_id="demo", module="eprf", data_kind="estimated",
                          return_period_years=100),
    total_depth_mm=80.0,
    duration_hours=1.0,
    peak_intensity_mm_h=80.0,
    hyetograph_mm=[20, 40, 20],
    timestep_hours=1/3,
    temporal_pattern="triangular",
)
dem = np.load(...)  # or construct
result = rainfall_forcing_to_hydraulic_run(forcing, dem, bounds=(...), dx=30, dy=30)
assert result.is_provisional()
print(label_depth_product(result.max_depth_m))
```

---

## Version

ROZVI **0.4.0**

Next candidates: Phase 6 asset/road risk (only if data interfaces exist), or Phase 7 uncertainty/provenance consolidation.
