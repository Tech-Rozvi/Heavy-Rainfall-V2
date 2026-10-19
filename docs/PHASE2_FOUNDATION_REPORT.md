# Phase 2 Foundation — Implementation Report

**Date:** 2026-10-07  
**Platform version:** ROZVI 0.1.0  
**EPRF engine version:** 8.1.0

---

## Implemented

| Item | Evidence |
|------|----------|
| Single version identity | `src/rozvi/__init__.py` — ROZVI 0.1.0, EPRF 8.1.0 |
| Authoritative README | `README.md` (legacy moved to `README_LEGACY_susceptibility.md`) |
| Unified config | `config/rozvi.yaml` + `src/rozvi/config.py` |
| Formal provenance | `src/rozvi/provenance.py` |
| Data QC (flag, no silent repair) | `src/rozvi/qc.py` |
| AOI wiring into CLI | `main.py` — `--point`, `--bbox`, `--crs`, `--buffer-km`; orchestrator |
| Orchestration helpers | `src/rozvi/orchestrator.py` |
| Empty package cleanup | Removed empty `src/eprf/{climate,data,ensemble,io}` |
| EVT consolidation note | `src/statistics/evt_return_periods.py` deprecated as canonical |
| CI workflow | `.github/workflows/ci.yml` |
| Foundation tests | `tests/test_rozvi_foundation.py` (9 tests) |

## Test results (this environment)

```
tests/test_rozvi_foundation.py
  PASSED: versions, config load, config validation, provenance, QC negatives/extremes,
          QC all-nan, QC CRS
  FAILED (env): resolve_aoi_bbox, write_manifest
    → ModuleNotFoundError: geopandas (PyPI mirror 502 at test time)
```

AOI unit tests in `tests/eprf/test_aoi.py` **passed in the prior session** when geopandas was installed. Re-run after `pip install geopandas`.

## Files created

- `src/rozvi/__init__.py`
- `src/rozvi/provenance.py`
- `src/rozvi/qc.py`
- `src/rozvi/config.py`
- `src/rozvi/orchestrator.py`
- `config/rozvi.yaml`
- `tests/test_rozvi_foundation.py`
- `.github/workflows/ci.yml`
- `docs/PHASE2_FOUNDATION_REPORT.md`
- `README.md` (new authoritative)

## Files modified

- `src/eprf/__init__.py` — version 8.1.0
- `src/statistics/evt_return_periods.py` — deprecation notice
- `main.py` — ROZVI config default, point/bbox/crs/buffer CLI, AOI orchestrator
- `api/app.py` — version 0.1.0
- `run_eprf.py` — version strings 8.1

## Files moved / removed

- `README.md` → `README_LEGACY_susceptibility.md`
- Empty dirs: `src/eprf/climate`, `data`, `ensemble`, `io`

## Still deferred (not Phase 2)

- Multi-source fusion / bias correction (Phase 3)
- Hydrology extraction (Phase 4)
- Asset / road risk (Phase 6)
- Full-chain uncertainty (Phase 7)
- Docker image
- API endpoints for EPRF products

## How to verify locally

```bash
pip install -r requirements.txt
python -m pytest tests/test_rozvi_foundation.py tests/eprf/test_aoi.py -v
python -c "from src.rozvi import __version__; print(__version__)"
python main.py --help   # shows --point --bbox --crs --buffer-km
```
