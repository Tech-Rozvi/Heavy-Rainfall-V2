# Legacy products and deprecation map

**ROZVI 0.9.0**

## Canonical stack (prefer these)

| Need | Module / API |
|------|----------------|
| AOI / point | `src.eprf.aoi`, CLI `--point` / `--bbox` / `--aoi` |
| Extremes / return periods | `src.eprf.extremes`, `POST /v1/rozvi/return-periods` |
| Design storm forcing | `src.eprf.design_storm`, `RainfallForcing` |
| Event hydrology | `src.hydrology`, `POST /v1/rozvi/event-hydrology` |
| Flood depth (provisional) | `src.hydraulics` via `rainfall_forcing_to_hydraulic_run` |
| Physical exposure | `src.risk` |
| Uncertainty chain | `src.rozvi.chain`, `POST /v1/rozvi/chain` |

## Legacy / diagnostic only

| Product | Location | Status |
|---------|----------|--------|
| Weighted-overlay susceptibility score [0,1] | `main.run_pipeline`, `HeavyRainSusceptibilityModel` | **Legacy diagnostic** |
| AHP weighting helpers | `src/weighting.py` | Supporting legacy path |
| Older README_V4 / V6 / EPRF_v7 notes | repo root | Historical |

### Rules for the legacy susceptibility path

1. Outputs must carry `product_label=legacy_relative_susceptibility`.
2. Must set `is_flood_depth=false` (and equivalent metadata).
3. Must log `SUSCEPTIBILITY_DISCLAIMER` from `src.rozvi.legacy`.
4. Must not be fed into hydraulics as rainfall depth.
5. Must not appear in risk reports as flood hazard without relabelling.

## Removed / never claimed

- Financial / insured loss
- Event-validated regulatory flood maps (in this repository alone)
- Dynamical downscaling executed inside ROZVI
