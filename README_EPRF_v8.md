# Extreme Precipitation Risk Framework (EPRF) v8.0.0

Professional, modular climate and extreme-precipitation analysis framework.

## Four pillars of this release

1. **Universal AOI / point input** — GeoJSON, Shapefile/ZIP, GPKG, KML, CSV, Excel, WKT, bbox, point; CRS discipline with confidence scoring.
2. **Return periods with mandatory uncertainty** — GEV + bootstrap CIs; extrapolation ratio and confidence class when T exceeds record length.
3. **Hydraulics integration** — Formal `RainfallForcing` contract and bridge; rainfall model never fabricates flood depth.
4. **Transparent climate framework** — Delta change, multi-model ensemble percentiles, CORDEX/WRF product registry (no fake dynamical downscaling).

## Quick start

```bash
pip install -r requirements.txt

# Unit tests (AOI, return periods, design storms, climate, interfaces)
python -m pytest tests/eprf/ -v

# Example: point analysis around Harare
python -c "
from src.eprf import point_to_aoi, PointMode, aoi_diagnostic_report
aoi = point_to_aoi(31.05, -17.83, crs='EPSG:4326', mode=PointMode.BUFFER, buffer_km=25)
print(aoi_diagnostic_report(aoi))
"

# Example: return periods with uncertainty table
python -c "
import numpy as np
from src.eprf.extremes.return_period_report import report_return_periods_1d, format_return_period_table
am = np.random.default_rng(0).gumbel(40, 10, size=30)
print(format_return_period_table(report_return_periods_1d(am, n_bootstrap=50)))
"
```

## Module map

```
src/eprf/
  aoi/           Universal ingestion, point mode, diagnostics
  extremes/      GEV, POT, rich return-period reports
  design_storm/  Hyetographs for hydraulic forcing
  idf/           IDF/DDF (daily-safe; sub-daily opt-in)
  climate_v2/    Transparent delta, ensemble, CORDEX registry
  interfaces/    RainfallForcing, ClimateAdjustment, HydraulicResult, bridge
  features/      ETCCDI indices
  validation/    Metrics + blocked CV
  uncertainty/   Bootstrap + quality flags
```

## Documentation

- `docs/CAPABILITY_MATRIX_v8.md` — full audit and status of every capability
- `docs/SCIENTIFIC_AUDIT_v7.md` — prior scientific audit (still valid)
- `docs/METHODOLOGY_v7.md` — EVT and indices methodology

## Scientific statement

EPRF v8 produces AOI-normalized analyses, extreme-value return levels with explicit uncertainty and extrapolation flags, design-storm rainfall forcing for a separate hydraulics module, and transparent climate adjustments. It does not claim numerical weather prediction skill, dynamical downscaling, or flood inundation. Confidence is derived from measurable criteria (record length, extrapolation ratio, CI width), not marketing labels.

---
Version 8.0.0
