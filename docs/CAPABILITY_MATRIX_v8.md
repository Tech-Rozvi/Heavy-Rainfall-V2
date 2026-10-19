# EPRF v8.0.0 — Capability Matrix & Final Audit

## What existed before (v7)

- Weighted-overlay susceptibility (diagnostic)
- ETCCDI indices
- Basic GEV return levels with bootstrap
- Simple CMIP6 scalar delta table
- Separate 2-D hydraulics solver
- Local / remote data acquisition stubs
- Limited AOI handling (GeoJSON / GAUL country-province)

## What was added in v8

| Component | Path |
|-----------|------|
| Universal AOI ingestion | `src/eprf/aoi/ingest.py` |
| Point mode | `src/eprf/aoi/point.py` |
| AOI diagnostics | `src/eprf/aoi/diagnostics.py` |
| Rich return-period reports | `src/eprf/extremes/return_period_report.py` |
| Design storm generator | `src/eprf/design_storm/generator.py` |
| IDF (daily-safe) | `src/eprf/idf/curves.py` |
| Inter-module contracts | `src/eprf/interfaces/contracts.py` |
| Hydraulics bridge | `src/eprf/interfaces/hydraulics_bridge.py` |
| Transparent climate delta | `src/eprf/climate_v2/delta.py` |
| Climate ensemble | `src/eprf/climate_v2/ensemble.py` |
| CORDEX/WRF registry | `src/eprf/climate_v2/cordex_interface.py` |
| Tests | `tests/eprf/test_aoi.py`, `test_return_period_report.py`, `test_design_storm_and_interfaces.py` |

## What was changed

- Package version → 8.0.0
- `__init__.py` exports AOI API
- Requirements: geopandas, pyogrio, pyproj, openpyxl confirmed

## What remains incomplete / external

| Item | Status | Notes |
|------|--------|-------|
| Full multi-source gauge–satellite merging | Interface only | Needs national gauge archive |
| Non-stationary GEV with covariates | Not implemented | Designed extension |
| Regional frequency analysis (L-moments) | Not implemented | Designed extension |
| True dynamical downscaling (WRF) | External only | CORDEX/WRF *registration* interface provided |
| Sub-daily IDF from observations | Requires sub-daily data | Daily path refuses silent invention |
| Spatial extremes (max-stable) | Not implemented | Documented future work |
| Full end-to-end flood depth for arbitrary AOI | Requires hydraulics module + DEM | Bridge implemented; solver is separate |

## Capability matrix

| Capability | Status | Evidence | Limitations |
|------------|--------|----------|-------------|
| AOI upload (GeoJSON, GPKG, SHP/ZIP, CSV, XLSX, KML, WKT) | **Implemented** | `ingest.py` + tests | KMZ depends on driver; GML best-effort |
| Point analysis | **Implemented** | `point.py` + tests | Buffer uses Web Mercator approximation |
| BBox input | **Implemented** | `ingest_aoi(bbox=...)` | — |
| CRS handling | **Implemented** | Explicit confidence levels; no silent guess for projected coords | Geographic inference flagged low-confidence |
| AOI diagnostics | **Implemented** | `aoi_diagnostic_report` | Data-coverage signals need catalogue injection |
| Rainfall estimation (indices) | **Implemented** | ETCCDI module | — |
| Heavy / extreme rainfall | **Implemented** | Indices + GEV | — |
| Return periods (2–1000 y) | **Implemented** | `return_period_report.py` | Confidence collapses for long T |
| Long return periods | **Implemented with flags** | Extrapolation ratio + confidence class | Not high-confidence beyond ~2× record |
| Uncertainty (bootstrap CI) | **Implemented** | Mandatory on every RP result | Structural uncertainty not fully quantified |
| IDF | **Partial** | Daily 24/48/72 h; sub-daily only with explicit opt-in | Sub-daily = estimated, labelled |
| Design storms | **Implemented** | Uniform, alternating-block, Chicago, front/back loaded | Regional patterns need calibration |
| CMIP6 delta | **Implemented** | `climate_v2.delta` + ensemble table loader | Scalar / relative; not spatial fields by default |
| CORDEX interface | **Implemented (registry)** | `cordex_interface.py` | Does not download or run RCMs |
| Climate scenarios (SSP) | **Implemented** | Config + ensemble | Depends on supplied tables/products |
| Delta change | **Implemented** | Absolute / relative | Explicitly not dynamical downscaling |
| Bias correction | **Interface only** | Notes in climate contracts | Full QM needs observation–model pairs |
| Dynamical downscaling | **External interface** | CORDEX/WRF registration | Computation is out of scope |
| Flood forcing export | **Implemented** | `RainfallForcing` + design storm | — |
| Flood depth integration | **Bridge implemented** | `hydraulics_bridge.py` | Requires DEM + hydraulics solver run |
| Inundation integration | **Via hydraulics module** | Same bridge | Rainfall model never fabricates depth |
| Validation metrics | **Implemented** | NSE, KGE, POD, FAR, CSI, … | — |
| Reproducibility | **Implemented** | Provenance, seeds, config, tests | — |

## What can run locally

- AOI ingestion (vector/point/bbox)
- ETCCDI indices
- GEV return periods + uncertainty table
- Design storms
- Daily IDF
- Climate delta application
- Unit tests (15 new + prior EPRF tests)

## What requires external data / compute

- Multi-decadal station series for high-confidence long return periods
- Sub-daily observations for true sub-daily IDF
- CORDEX / WRF NetCDF products for dynamical-downscaling pathway
- National DEM + land-surface parameters for full hydraulic runs
- Cloud / HPC for continental-scale raster stacks

## Scientific integrity rules enforced in code

1. CRS confidence is never silently assumed for projected coordinates.
2. Return periods beyond the record are labelled EXTRAPOLATED with reduced confidence.
3. Delta change is labelled “NOT dynamical downscaling”.
4. Rainfall forcing carries `data_kind` and refuses to be mistaken for flood depth.
5. Sub-daily IDF from daily data is opt-in and labelled estimated.
6. Every inter-module payload carries AOI ID, timestamp, units, scenario, confidence.

---

**Version 8.0.0** — Extreme Precipitation Risk Framework  
Rainfall and extreme-precipitation engine for a modular climate-risk platform.
