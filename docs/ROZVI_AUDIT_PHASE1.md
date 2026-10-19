# ROZVI Phase 1 — Full Repository Audit

**Audit date:** 2026-10-07  
**Repository audited:** Heavy-Rainfall-Model / EPRF (intended foundation for ROZVI)  
**Auditor role:** Scientific software architecture / hydroclimatology / flood-risk / QA  
**Status:** AUDIT ONLY — no implementation changes in this phase

---

## 0. Naming and identity

| Claimed identity | Where | Notes |
|------------------|-------|-------|
| Heavy Rainfall Susceptibility Model | README.md, config | Original product |
| Heavy-Rainfall-Model v4 | main.py | CLI entry |
| API version 5.0.0 | api/app.py | FastAPI |
| config version 2.1.0 | config/config.yaml | — |
| default_config version 4.0 | config/default_config.yaml | — |
| EPRF v7.0.0 | docs, run_eprf.py, eprf_config | Extreme Precipitation Risk Framework |
| EPRF v8.0.0 | src/eprf/__init__.py, README_EPRF_v8, CAPABILITY_MATRIX | Latest package version |
| **ROZVI** | **Not present in code or docs** | User intent only; no branding, package, or API uses this name |

**Finding:** There is no ROZVI codebase yet. The repository is a rainfall/susceptibility + partial hydraulics system with a parallel EPRF scientific layer. Version numbers are inconsistent across entry points.

---

## 1. Current architecture map

```
┌─────────────────────────────────────────────────────────────────────┐
│ ENTRY POINTS (not unified)                                          │
│  main.py (v4 CLI)  │  run_eprf.py (v7 CLI)  │  api/app.py (v5 API) │
└─────────┬──────────────────┬───────────────────────┬────────────────┘
          │                  │                       │
          ▼                  ▼                       ▼
┌─────────────────┐  ┌──────────────────┐  ┌────────────────────┐
│ LEGACY PATH     │  │ EPRF PATH (v7/v8)│  │ FASTAPI UI         │
│ DataAcquisition │  │ aoi/             │  │ static HTML/JS     │
│ manager         │  │ extremes/        │  │ /health, bbox runs │
│ Weighted overlay│  │ features/        │  └────────────────────┘
│ susceptibility  │  │ design_storm/    │
│ rainfall_indices│  │ idf/             │
│ weighting (AHP) │  │ climate_v2/      │
│ classification  │  │ interfaces/      │
└────────┬────────┘  │ pipeline.py      │
         │           └────────┬─────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌──────────────────┐
│ HYDRAULICS      │  │ contracts        │
│ solver2d (SWE)  │◄─│ RainfallForcing  │  (bridge exists; lightly wired)
│ multi_peril     │  │ hydraulics_bridge│
│ forecast_run    │  └──────────────────┘
│ CN / Green-Ampt │
│ (embedded)      │
└─────────────────┘

MISSING FROM TARGET ARCHITECTURE:
  • Formal data QC layer
  • Multi-source rainfall fusion
  • Standalone hydrology (losses → excess → runoff → hydrograph)
  • Exposure / vulnerability / consequence / risk modules
  • Asset-level and road-corridor workflows
  • Formal provenance registry
  • Unified configuration
  • Docker / CI / database
  • One authoritative public API contract
```

### Data flow (as implemented today)

1. **Legacy CLI (`main.py`)**  
   AOI (GeoJSON/GAUL) → `DataAcquisitionManager` (local npy/tif or remote CHIRPS/ERA5/DEM) → simple MAP/Rx1/p95 normalisation → ad-hoc weighted susceptibility → optional forecast hydraulics → GeoTIFF + JSON reports.

2. **EPRF CLI (`run_eprf.py`)**  
   Local daily precip cube → ETCCDI indices → GEV return levels → quality flags → provenance JSON.  
   AOI module (`src/eprf/aoi`) is **not** called by `run_eprf.py` or `main.py`.

3. **API (`api/app.py`)**  
   Browser UI → bbox / country → triggers acquisition + pipeline similar to main. Does not expose EPRF return-period or design-storm endpoints.

4. **Hydraulics**  
   DEM + design rainfall parameters → 2D shallow-water solver → depth raster. Curve Number / optional Green-Ampt live **inside** the hydraulics package, not as a separate hydrology stage.  
   EPRF `RainfallForcing` → `hydraulics_bridge` exists but is not the default production path.

---

## 2. Module inventory

### 2.1 Legacy core (`src/`)

| Module | Role | Status |
|--------|------|--------|
| `model.py` | Susceptibility weighted overlay + optional ML predictor | Implemented; susceptibility is primary |
| `weighting.py` | AHP + RF permutation importance | Implemented; unit tests |
| `classification.py` | Minmax/zscore/percentile standardisation | Implemented; unit tests |
| `rainfall_indices.py` | ETCCDI indices | Implemented; unit tests |
| `correlation.py` | Pearson/Spearman/VIF | Implemented; unit tests |
| `preprocessing.py` | Reproject/resample/align | Implemented; limited tests |
| `terrain.py` | Slope, aspect exposure, CN helper | Implemented |
| `validation.py` | Station-point validation helpers | Implemented; thin |
| `uncertainty.py` | Monte Carlo on weights | Implemented |
| `visualization.py` | Plotting helpers | Implemented |
| `statistics/evt_return_periods.py` | Gumbel/GEV return periods | **Duplicated** by EPRF extremes |
| `climate/cmip6_projection.py` | Scalar/table delta change | **Partially superseded** by climate_v2 |
| `data/manager.py` | Acquisition orchestration | Implemented |
| `data/streaming/*` | Remote CHIRPS/ERA5/DEM/surface | Implemented; network-dependent |
| `data/zimbabwe_aoi.py` | GAUL/country AOI helpers | Country-specific; conflicts with AOI independence goal |
| `hydraulics/*` | 2D SWE, multi-peril, forecast, CN/GA | Implemented; not fully validated against observations |
| `reporting/*` | Site hazard HTML/JSON | Implemented |
| `generate_synthetic_data.py` | Synthetic demo data | Test/demo only |

### 2.2 EPRF layer (`src/eprf/`) — v8

| Module | Role | Status |
|--------|------|--------|
| `aoi/` | Universal AOI/point/bbox ingestion, diagnostics | Implemented + tested |
| `extremes/gev.py` | GEV AMS + bootstrap | Implemented + tested |
| `extremes/pot.py` | GPD POT | Implemented |
| `extremes/return_period_report.py` | Rich RP table, extrapolation flags | Implemented + tested |
| `features/indices.py` | ETCCDI (non-circular) | Implemented + tested |
| `design_storm/` | Hyetograph generator | Implemented + tested |
| `idf/` | Daily IDF; sub-daily opt-in labelled | Implemented + tested |
| `climate_v2/` | Delta, ensemble, CORDEX registry | Implemented + tested |
| `interfaces/` | RainfallForcing, ClimateAdjustment, HydraulicResult, bridge | Implemented + tested |
| `validation/` | Metrics + blocked CV | Implemented |
| `uncertainty/` | Bootstrap wrapper + quality flags | Implemented |
| `pipeline.py` | EPRF end-to-end on precip cube | Implemented |
| `climate/`, `data/`, `ensemble/`, `io/` | **Empty directories** | Placeholder debt |

### 2.3 API / frontend

| Component | Status |
|-----------|--------|
| FastAPI app | Runs; version label 5.0.0 |
| Static UI | Basic HTML/JS form |
| OpenAPI | Auto from FastAPI |
| EPRF endpoints | **Missing** |
| Auth | None |
| Job queue / async | None |

### 2.4 Config

| File | Version claim | Notes |
|------|---------------|-------|
| `config/config.yaml` | 2.1.0 | Full factor/weighting config |
| `config/default_config.yaml` | 4.0 | Slimmer production defaults |
| `config/eprf/eprf_config.yaml` | 7.0.0 | EPRF-specific (version string outdated vs package 8.0.0) |
| `config/hydraulics.yaml` | — | Hydraulics parameters |

**Finding:** Three competing configuration systems; no single validated schema.

---

## 3. Scientific methodology inventory

| Capability | Method present | Scientifically labelled | Validated against observations? |
|------------|----------------|-------------------------|----------------------------------|
| Relative rainfall susceptibility | Weighted overlay (AHP / RF) | Yes (README) | Partial (synthetic/mixed stations) |
| ETCCDI indices | Rx1day, Rx5day, R95p, … | Yes | Computational tests only |
| Extreme value (AMS/GEV) | MLE + bootstrap CI | Yes; extrapolation flags in v8 | Unit tests; **not** event-validated |
| POT/GPD | Implemented | Partial docs | Unit-level only |
| Non-stationary EVT | **Absent** | — | — |
| Regional frequency analysis | **Absent** | — | — |
| Spatial extremes | **Absent** (pixel-independent GEV) | Limitation documented | — |
| IDF/DDF | Daily 24/48/72 h; sub-daily estimated | Explicit limits | Synthetic only |
| Design storms | Uniform, alternating-block, Chicago, front/back | Yes | Not calibrated regionally |
| Climate delta change | Relative/absolute scalar | Explicitly not dynamical DS | Table-driven; not validated |
| CORDEX/WRF | Registry only | Correctly labelled external | No products loaded |
| Bias correction / fusion | **Absent** as operational module | Mentioned in contracts only | — |
| Hydrology (losses→runoff→hydrograph) | CN + optional Green-Ampt **inside hydraulics** | Mixed with hydraulics | Not separately validated |
| 2D hydraulics | SWE solver | Present | Demo outputs; no observed flood validation |
| Exposure / vulnerability / risk | Exposure report helpers only | Incomplete | — |
| Asset / road risk | **Absent** | — | — |

---

## 4. Dependency inventory

### Python packages (requirements.txt)
numpy, scipy, xarray, rioxarray, rasterio, fsspec, zarr, s3fs, gcsfs, requests, geopandas, shapely, pyogrio, pyproj, openpyxl, pyyaml, numba, scikit-learn, matplotlib, fastapi, uvicorn, httpx, planetary-computer, pystac-client, jinja2

### Missing for target ROZVI
- Database driver / ORM (none)
- Job queue (Celery/RQ/none)
- Auth
- Docker base image definition
- CI config
- Formal schema validation library usage (pydantic used only in API models partially)

### Runtime data dependencies
- Bundled synthetic `daily_precip.npy` (~3 years, 60×60) — **too short for high return periods**
- Small DEM/terrain tifs
- Optional remote: CHIRPS, ERA5 Zarr, Copernicus DEM (network + credentials/access)
- GAUL boundaries directory (empty in tree)

---

## 5. Documentation inventory

| Document | Purpose | Accuracy vs code |
|----------|---------|------------------|
| README.md | Original susceptibility model | Partially accurate; does not describe EPRF v8 |
| README_V4.md | Short v4 note | Obsolete |
| README_V6.md | Short v6 note | Obsolete |
| README_EPRF_v7.md | EPRF v7 guide | Superseded by v8 |
| README_EPRF_v8.md | EPRF v8 guide | Accurate for EPRF layer |
| INTEGRATION.md | Integration notes | Thin |
| api/README_UI.md | UI notes | Thin |
| docs/SCIENTIFIC_AUDIT_v7.md | Scientific audit | Valid for pre-v8 issues |
| docs/METHODOLOGY_v7.md | Methodology | Valid for EVT/indices |
| docs/CHANGELOG_v7.md | Changelog | Partial |
| docs/CAPABILITY_MATRIX_v8.md | Capability status | Most accurate current snapshot |

**Finding:** Multiple READMEs; no single authoritative system README; ROZVI name absent; version contradictions.

---

## 6. Test inventory

| Suite | Count | Covers | Gaps |
|-------|-------|--------|------|
| `tests/test_*.py` | 4 files | weighting, classification, correlation, rainfall_indices | No main.py integration; no hydraulics; no data manager |
| `tests/eprf/*` | 5 files, 15+ tests | AOI, GEV, RP report, design storm, climate, interfaces, indices, pipeline | No remote acquisition; no real gauge validation; no hydraulic solver tests |
| Scientific / known-event tests | **0** | — | Critical gap |
| End-to-end production path tests | **0** | — | main.py + API untested in CI |
| Regression benchmarks | **0** | — | — |

**Docker / CI / CD:** None present.

---

## 7. What currently works

1. Loading local daily precip and computing ETCCDI indices.  
2. GEV annual-maxima fits with bootstrap CIs and extrapolation confidence rules (EPRF).  
3. Universal AOI ingestion (vector/point/bbox) with CRS confidence (EPRF; not wired to main CLI).  
4. Design-storm hyetographs and `RainfallForcing` contract.  
5. Transparent climate delta application and CORDEX product registration.  
6. Basic FastAPI health + UI shell.  
7. 2D SWE hydraulic solver code path (demo).  
8. Unit tests for EPRF modules and selected legacy modules (pass when deps installed).

---

## 8. What partially works

1. Data acquisition (remote path network-dependent; local synthetic works).  
2. Susceptibility weighted overlay (works; scientifically limited as ranking only).  
3. Hydraulics–rainfall bridge (code exists; not default workflow).  
4. Climate projections (scalar deltas only; no spatial ensemble fields).  
5. Validation metrics module (exists; rarely applied to real independent observations).  
6. Provenance JSON in EPRF pipeline (ad-hoc, not formal schema-wide).

---

## 9. What is duplicated

| Concern | Locations | Risk |
|---------|-----------|------|
| EVT / return periods | `src/statistics/evt_return_periods.py` vs `src/eprf/extremes/*` | Divergent behaviour |
| Climate delta | `src/climate/cmip6_projection.py` vs `src/eprf/climate_v2/*` | Two sources of truth |
| Uncertainty | `src/uncertainty.py` vs `src/eprf/uncertainty/*` | Incomplete propagation |
| Validation | `src/validation.py` vs `src/eprf/validation/*` | Split metrics |
| Rainfall indices | `src/rainfall_indices.py` vs `src/eprf/features/indices.py` | Drift |
| Config | 3 YAML trees | Inconsistent runs |
| README / version story | 5+ README files | User confusion |

---

## 10. What is obsolete or empty

- `README_V4.md`, `README_V6.md` — superseded  
- `requirements_v4.txt` — superseded  
- Empty packages: `src/eprf/climate`, `src/eprf/data`, `src/eprf/ensemble`, `src/eprf/io`, `schemas/`  
- `src/data/zimbabwe_aoi.py` as hard dependency conflicts with geography-independence goal (retain as optional helper only)

---

## 11. Scientifically questionable areas

1. **Susceptibility score using precip-derived indices as predictors** (partially fixed in EPRF; still present in legacy `main.py` path).  
2. **Short synthetic record (~3 years)** used in demos while discussing 100–500 year return levels — EPRF correctly flags this; legacy path may not.  
3. **Pixel-independent GEV** ignores spatial storm structure.  
4. **CN/Green-Ampt inside hydraulics** without a validated, separate hydrology stage or observed discharge.  
5. **No bias correction / multi-source fusion** before extremes.  
6. **Climate scalars** applied without clear mapping to extremes vs means in all paths.  
7. **No observed flood extent/depth validation** for the SWE solver.

---

## 12. Engineering risks

| Risk | Severity |
|------|----------|
| Dual entry points / dual architectures not integrated | High |
| Version number chaos | High (reproducibility) |
| No CI | High |
| No formal QC layer | High |
| Hydraulics untested in automated suite | High |
| Empty packages suggest unfinished design | Medium |
| Country-specific AOI helper | Medium |
| No database / job system for scale | Medium (for platform goals) |
| API does not expose EPRF capabilities | Medium |
| Documentation contradicts code versions | Medium |

---

## 13. Gap analysis (target architecture vs current)

| Layer | Status | Priority | Notes |
|-------|--------|----------|-------|
| AOI & data ingestion | PARTIALLY IMPLEMENTED | P0 | EPRF AOI good; not wired to main/API |
| Data QC & harmonisation | MISSING | P0 | Critical foundation |
| Rainfall reconstruction / fusion | MISSING | P0 | Only single-source paths |
| Bias correction | MISSING / INTERFACE ONLY | P0 | — |
| Extreme rainfall & EVT | IMPLEMENTED BUT NEEDS VALIDATION | P0 | EPRF GEV/POT; needs real data validation |
| Spatial extremes | MISSING | P1 | Documented limitation |
| Forecasting / design storms / IDF | PARTIALLY IMPLEMENTED | P1 | Design storm + daily IDF; no regional calibration |
| Climate change & ensembles | PARTIALLY IMPLEMENTED | P1 | Delta + registry; no full ensemble pipeline |
| Hydrology (losses→runoff→hydrograph) | PARTIALLY IMPLEMENTED / MIXED | P0 | Embedded in hydraulics; must separate |
| Hydraulics | IMPLEMENTED BUT NEEDS VALIDATION | P1 | 2D SWE exists |
| Flood depth/extent/velocity/duration | PARTIAL (depth) | P1 | Velocity/duration incomplete |
| Exposure | PARTIAL | P2 | Report helpers only |
| Vulnerability / consequence | MISSING | P2 | — |
| Risk (H×E×V) | MISSING | P2 | Susceptibility ≠ risk |
| Asset-level results | MISSING | P2 | — |
| Road corridor modelling | MISSING | P2 | — |
| Uncertainty propagation (full chain) | PARTIAL (rainfall/EVT only) | P1 | — |
| Confidence framework | PARTIAL | P1 | Record-length based; not full pipeline |
| Explainability | PARTIAL | P2 | SHAP optional in legacy; not systematic |
| Provenance system | PARTIAL | P0 | Ad-hoc JSON |
| Validation framework | PARTIAL | P0 | Metrics exist; no known-event suite |
| API contracts | PARTIAL / FRAGILE | P1 | FastAPI models incomplete |
| Config coherence | CONTRADICTORY | P0 | — |
| Documentation (single README) | CONTRADICTORY | P0 | — |
| Tests (layered) | PARTIAL | P0 | — |
| Docker / CI / scale | MISSING | P1 | — |

---

## 14. Risk register (scientific + engineering)

| ID | Risk | Type | Severity | Mitigation direction |
|----|------|------|----------|----------------------|
| R1 | Presenting susceptibility as flood hazard | Scientific | Critical | Enforce separation; API/docs gates |
| R2 | Long return periods without extrapolation flags on legacy path | Scientific | Critical | Unify on EPRF RP reporter |
| R3 | Unvalidated hydraulics labelled as production flood depth | Scientific | High | Validation gate; label provisional |
| R4 | Dual code paths diverge | Engineering | High | Single orchestration layer |
| R5 | No QC → silent bad data | Scientific/Eng | High | QC module before fusion |
| R6 | No fusion/bias correction | Scientific | High | Benchmarked fusion module |
| R7 | Version/provenance inconsistency | Reproducibility | High | Single version + provenance schema |
| R8 | Empty packages / dead docs | Maintainability | Medium | Remove or implement |
| R9 | No CI | Engineering | High | Add minimal CI running unit tests |
| R10 | Synthetic data mistaken for calibrated product | Scientific | High | Hard flags in outputs |

---

## 15. Recommended implementation sequence

Aligned with the user’s PHASE plan, **constrained by current repo reality**:

### PHASE 1 — AUDIT (this document)  
**Status: COMPLETE**

### PHASE 2 — FOUNDATION (next)
1. Single version identity (e.g. ROZVI 0.1.0 / EPRF 8.1) and one authoritative README.  
2. Wire EPRF AOI into `main.py` and API; deprecate silent CRS assumptions.  
3. Unified config schema (one tree, validated).  
4. Formal provenance dataclass used by all outputs.  
5. Minimal data QC module (gaps, impossible values, CRS checks) with flags, no silent repair.  
6. Remove or quarantine empty packages; consolidate duplicate EVT/climate entry points (re-export, don’t fork).  
7. CI: run `pytest tests/` on PR.

### PHASE 3 — SCIENTIFIC CORE
1. Multi-source rainfall interface + bias-correction benchmarks (start with quantile mapping vs linear scaling).  
2. Unify EVT on EPRF reporter; retire duplicate or make thin wrappers.  
3. Known-event / gauge validation harness (even if data must be user-supplied).  
4. IDF/design storm regional notes and clear daily-data limits (already partial).

### PHASE 4 — HYDROLOGY
1. Extract CN/Green-Ampt/loss models from hydraulics into `src/hydrology/`.  
2. Explicit excess rainfall → simple hydrograph interface.  
3. Validation hooks for discharge where data exist.

### PHASE 5 — HYDRAULICS
1. Consume hydrology hydrographs / design storms only via contracts.  
2. Automated smoke tests for solver; label outputs provisional until event-validated.

### PHASE 6 — RISK
1. Exposure schema (assets, roads).  
2. Vulnerability curves (configurable, not hard-coded magic).  
3. Risk = f(hazard, exposure, vulnerability) with units and confidence.

### PHASE 7–10
Uncertainty propagation, benchmarking, API stabilisation, cleanup — as data and validation allow.

---

## 16. Decision: preserve vs refactor vs remove

| Component | Action |
|-----------|--------|
| EPRF AOI, extremes, design_storm, idf, climate_v2, interfaces | **Preserve and promote** to system core |
| Legacy susceptibility model | **Preserve as diagnostic product only**; never as flood hazard |
| Hydraulics SWE | **Preserve**; separate hydrology; add tests; provisional label |
| Duplicate EVT/climate/validation | **Consolidate** (EPRF canonical; legacy wrappers) |
| zimbabwe_aoi | **Preserve as optional locale helper** |
| README_V4/V6, requirements_v4 | **Remove** after single README |
| Empty eprf subpackages | **Remove** until needed |
| main.py / run_eprf.py / api | **Refactor toward one orchestrator** |
| Synthetic data path | **Preserve for tests only**; block in production config default |

---

## 17. Explicit non-claims (audit conclusion)

This repository today **does not**:
- Implement ROZVI as a named platform  
- Provide multi-source calibrated rainfall fusion  
- Provide a standalone, validated hydrology stage  
- Provide asset- or road-level risk  
- Provide full-chain uncertainty propagation  
- Provide observed-event validation of flood depth  
- Provide Docker/CI/database-backed multi-user operation  
- Guarantee reproducible national-scale runs from a single config  

It **does** provide usable building blocks for rainfall extremes, AOI handling, design storms, transparent climate deltas, and a research-grade 2D hydraulics solver that must remain clearly separated from rainfall susceptibility.

---

## 18. Next step (awaiting approval to implement)

Per instructions: **no implementation in this phase.**

Proposed immediate work when Phase 2 is authorised:
1. Authoritative README + version unification  
2. Config consolidation  
3. Provenance + QC foundation modules  
4. Wire AOI → main/API  
5. Consolidate EVT/climate imports  
6. Minimal CI  
7. Technical debt register file in-repo  

---

*End of Phase 1 Audit. Implementation must not begin until this analysis is accepted as the baseline.*
