# Phase 3 — Scientific Core Implementation Report

**Date:** 2026-10-09  
**Platform:** ROZVI **0.2.0**  
**EPRF engine:** **8.2.0**

---

## Objectives (from audit)

1. Multi-source rainfall interface + bias-correction benchmarks  
2. Unify EVT on EPRF reporter  
3. Gauge / known-event validation harness  
4. Preserve IDF/design-storm daily-data limits (already in place)

---

## Implemented

### Bias correction (`src/eprf/bias/`)

| Method | Module | Notes |
|--------|--------|-------|
| Linear scaling | `methods.py` | Multiplicative mean match |
| Variance scaling | `methods.py` | Mean + variance match; clip ≥ 0 |
| Empirical quantile mapping | `methods.py` | Rank mapping; fallback to linear if n_cal < 5 |

**Benchmark** (`benchmark.py`): temporal hold-out (default last 30%); reports MAE, RMSE, bias, correlation, % RMSE improvement vs raw; selects best method by validation RMSE. **No claim that EQM is always best** — selection is evidence-based per dataset.

### Multi-source fusion (`src/eprf/fusion/`)

| Component | Role |
|-----------|------|
| `RainfallProduct` | Named array + kind (gauge/satellite/reanalysis/…) + metadata |
| `ProductCollection` | Set of products for one domain |
| `fuse_products` | `mean` / `weighted_mean` / `gauge_priority` |

Alignment is the **caller’s responsibility**. Fusion refuses incompatible shapes. Outputs are labelled `kind=fused`.

### Gauge validation harness (`src/eprf/validation/gauge_harness.py`)

- Load station CSV  
- Sample 2-D fields at points  
- Continuous + extreme metrics  
- Breakdown by `source` column  
- Explicit note when bundled coordinates may be synthetic  

### EVT unification

- `src/statistics/__init__.py` re-exports EPRF GEV / return-period report APIs  
- Legacy `evt_return_periods.py` remains for hydraulics compatibility (deprecated as canonical)

### Config

`config/rozvi.yaml` adds `bias_correction`, `fusion`, and `validation.station_csv`.

---

## What was deliberately not claimed

- Operational multi-satellite download/merge pipelines (interface only; products are user-supplied arrays)  
- Automatic “best method for all of Africa”  
- Spatial extremes / RFA (still Phase later)  
- Non-stationary EVT  
- That bundled `stations.csv` is a real national gauge archive  

---

## Tests

`tests/eprf/test_bias_and_fusion.py`:

- Linear scaling reduces mean bias  
- EQM / variance scaling run and stay non-negative  
- Benchmark returns a best method  
- Fusion mean and gauge-priority  
- Series + station-field validation  
- Load bundled station CSV  

---

## Files created

- `src/eprf/bias/__init__.py`, `methods.py`, `benchmark.py`  
- `src/eprf/fusion/__init__.py`, `products.py`, `fuse.py`  
- `src/eprf/validation/gauge_harness.py`  
- `tests/eprf/test_bias_and_fusion.py`  
- `docs/PHASE3_SCIENTIFIC_CORE_REPORT.md`  

## Files modified

- `src/rozvi/__init__.py` → 0.2.0 / 8.2.0  
- `src/eprf/__init__.py` → 8.2.0  
- `src/eprf/validation/__init__.py`  
- `src/statistics/__init__.py`  
- `config/rozvi.yaml`  
- `tests/test_rozvi_foundation.py` (version assertion)

---

## Example usage

```python
import numpy as np
from src.eprf.bias import benchmark_bias_methods, empirical_quantile_mapping
from src.eprf.fusion import RainfallProduct, ProductCollection, fuse_products, FusionMethod
from src.eprf.validation import load_station_csv, validate_field_against_stations

# Bias benchmark (paired series)
obs, mod = ...  # aligned 1-D
table = benchmark_bias_methods(obs, mod, holdout_fraction=0.3)
print(table.summary_text())

# Fusion
coll = ProductCollection()
coll.add(RainfallProduct("chirps", "satellite", chirps_arr))
coll.add(RainfallProduct("era5", "reanalysis", era5_arr))
fused = fuse_products(coll, method=FusionMethod.MEAN)

# Gauge harness
stations = load_station_csv("data/validation/stations.csv")
report = validate_field_against_stations(annual_map, stations)
```

---

## Validation status

| Item | Status |
|------|--------|
| Unit tests (synthetic bias/fusion) | Implemented |
| Benchmark on real multi-decadal gauges | **NOT VALIDATED** — requires user gauge archive |
| Fusion skill vs independent gauges | **NOT VALIDATED** |
| EVT unification | Code path unified; scientific validation unchanged from Phase 1–2 |

---

*Phase 3 complete. Next: Phase 4 Hydrology (separate losses → runoff → hydrograph).*
