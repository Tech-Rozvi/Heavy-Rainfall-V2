# Phase 6 — Risk / Asset Layer

**Date:** 2026-10-09  
**Platform:** ROZVI **0.5.0**

---

## Objective

Add address/asset query and road–hazard intersection while preserving:

```text
rainfall / extremes  ≠  flood depth  ≠  exposure  ≠  financial risk
```

---

## Implemented

### Package `src/risk/`

| Module | Role |
|--------|------|
| `assets.py` | `Asset`, `AssetCollection`, CSV/GeoJSON/coordinate loaders |
| `query.py` | Sample hazard layers at points/assets; inherit provisional status |
| `roads.py` | Road length vs depth thresholds (screening) |
| `report.py` | `RiskSnapshot` composer with mandatory disclaimers |

### Data

- Example assets: `data/assets/example_assets.csv`
- Config: `risk:` block in `config/rozvi.yaml` (`financial_loss: false`)

### Integration

- Existing `src/reporting/exposure.py` remains for OSM building counts
- Risk package is the structured asset/road API for the platform

---

## Tests

`tests/risk/test_risk_layer.py`

| Result | Count |
|--------|-------|
| Passed | 5 |
| Skipped | 1 (road intersection — requires geopandas) |

---

## Explicit non-claims

- **No** insured loss, damage ratios, or financial risk  
- **No** traffic disruption modelling  
- Asset locations are **user-supplied** (example CSV is illustrative)  
- Road metric is **screening-level** midpoint sampling  
- Inherits **provisional** status from depth products  

---

## Example

```python
from src.risk import load_assets_csv, query_assets_hazard, build_risk_snapshot
import numpy as np

assets = load_assets_csv("data/assets/example_assets.csv")
depth = np.load(...)  # provisional flood depth
results = query_assets_hazard(assets, {"flood_depth_m": depth}, bounds=bounds)
snap = build_risk_snapshot(
    "harare_demo",
    hazard_layers={"flood_depth_m": depth},
    hazard_validation_status="provisional",
    asset_results=results,
)
print(snap.to_dict()["disclaimers"])
```

---

## Version

ROZVI **0.5.0**

Next: Phase 7 — full-chain uncertainty + provenance consolidation (or stop and stabilise).
