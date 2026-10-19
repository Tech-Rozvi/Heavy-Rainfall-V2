# ROZVI Capability Matrix

**Platform:** ROZVI **0.9.0** · **EPRF:** 8.2.0  
**Status vocabulary:** IMPLEMENTED · VALIDATED · PROVISIONAL · NOT YET IMPLEMENTED

| Capability | Status | Evidence | Limitations |
|------------|--------|----------|-------------|
| AOI upload (vector) | IMPLEMENTED | `src/eprf/aoi/`, CLI `--aoi` | geopandas required; KMZ partial |
| Point analysis | IMPLEMENTED | `point_to_aoi`, CLI `--point` | Buffer modes are geometric, not catchment delineation |
| CRS handling | IMPLEMENTED | AOI diagnostics, CRS confidence | Silent CRS assumption deprecated; still needs explicit CRS for bare points |
| Rainfall estimation (local cube) | IMPLEMENTED | `run_eprf.py`, local `.npy` | Multi-source operational download not fully wired |
| Heavy rainfall indices (ETCCDI) | IMPLEMENTED | `src/eprf/features` | Depends on input series quality |
| Extreme rainfall (GEV) | IMPLEMENTED | `src/eprf/extremes` | Short records → low confidence by design |
| Return periods + uncertainty | IMPLEMENTED | `return_period_report.py` | Extrapolation flagged when T ≫ n |
| Long return periods (e.g. 500–1000 y) | PROVISIONAL | Same EVT path | Valid only as extrapolation with mandatory flags |
| Bias correction methods | IMPLEMENTED | `src/eprf/bias` | Skill is dataset-specific; needs hold-out |
| Multi-source fusion interface | IMPLEMENTED | `src/eprf/fusion` | Caller must align products; no auto-STAC merge |
| Gauge validation harness | IMPLEMENTED | `gauge_harness.py` | Bundled stations are not a national archive |
| IDF / design storms | IMPLEMENTED | `idf/`, `design_storm/` | Daily data limits apply; sub-daily needs user series |
| Hydrology (CN / Green–Ampt / UH) | IMPLEMENTED | `src/hydrology` | Not regionally calibrated |
| Discharge validation hooks | IMPLEMENTED | `validate_discharge.py` | Requires user Q(t); not auto-validated |
| Rainfall→hydraulics contract | IMPLEMENTED | `RainfallForcing`, bridge | Only path that may produce depth |
| 2D hydraulic solver | IMPLEMENTED | `solver2d.py` | Smoke-tested only |
| Flood depth products | PROVISIONAL | Bridge + GeoTIFF tags | **Not** event-validated in this repo |
| Climate delta (SSP) | IMPLEMENTED | `climate_v2/delta.py` | Not dynamical downscaling |
| CORDEX/WRF registry | IMPLEMENTED | interface only | External products; not run here |
| Asset / address query | IMPLEMENTED | `src/risk` | User-supplied assets |
| Road–hazard intersection | IMPLEMENTED | `roads.py` | Screening metric; needs geopandas |
| Financial / insured loss | NOT YET IMPLEMENTED | — | Explicitly out of scope |
| Full-chain uncertainty | IMPLEMENTED | `src/rozvi/chain.py` | Weakest-link; no invented depth CI |
| Provenance records | IMPLEMENTED | `provenance.py`, chain | Must be written by callers |
| QC (flag, no silent repair) | IMPLEMENTED | `src/rozvi/qc.py` | Thresholds configurable |
| Non-stationary EVT | NOT YET IMPLEMENTED | — | Research next step |
| Operational multi-decadal gauge fusion | NOT YET IMPLEMENTED | — | Needs external data agreements |
| Docker / cloud deploy recipe | NOT YET IMPLEMENTED | — | Local CLI/API only |
| Event-validated flood maps | NOT YET IMPLEMENTED | — | Requires observed flood events |

Legacy matrix: `docs/CAPABILITY_MATRIX_v8.md` (EPRF v8 era).

| Scientific HTTP API (info, RP, hydrology, chain) | IMPLEMENTED | `api/rozvi_routes.py`, `src/rozvi/api_handlers.py` | FastAPI required to serve; handlers testable without it |
| One-command verify script | IMPLEMENTED | `scripts/verify.sh` | Network-dependent remote data tests not included |

| Legacy susceptibility quarantine labels | IMPLEMENTED | `src/rozvi/legacy.py`, `main.run_pipeline` | Path still runnable; diagnostic only |

| Docker / Compose runtime packaging | IMPLEMENTED | `Dockerfile`, `docker-compose.yml` | Optional deps may be absent; core stack prioritized |
| Makefile developer targets | IMPLEMENTED | `Makefile` | Local convenience only |

| Event depth validation (HWM / CSI gate) | IMPLEMENTED | `src/hydraulics/validate_depth.py` | Requires user observations; design maps not auto-validated |
| event_validated GeoTIFF tags | IMPLEMENTED | `export_depth_geotiffs(..., validation_status=...)` | Only when evaluate_event_depth passes |
