# ROZVI 0.10.0

**Climate, extreme precipitation, flood-forcing, and physical-exposure intelligence platform**

Rainfall / extremes engine: **EPRF 8.2.0** · Optional 2D hydraulics · Physical exposure · Chain uncertainty

> Authoritative docs: this README · [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md) · [docs/SCIENTIFIC_CLAIMS.md](docs/SCIENTIFIC_CLAIMS.md)

---

## Purpose

ROZVI supports:

- AOI / point / bbox analysis with explicit CRS handling
- ETCCDI indices and GEV return levels with uncertainty and extrapolation flags
- Design storms as `RainfallForcing` for a **separate** hydraulics module
- Event hydrology (SCS-CN / Green–Ampt / unit hydrograph)
- Provisional flood depth simulation (smoke-tested; **not** event-validated here)
- Asset/address sampling and road-length exposure (physical metrics only)
- Weakest-link chain uncertainty and provenance

It does **not** claim NWP skill, dynamical downscaling, insured loss, or regulatory design-flood status.

---

## Architecture

```text
AOI / point → QC → rainfall indices / EVT → design storm
                      ↓
                 event hydrology
                      ↓
              RainfallForcing contract
                      ↓
           hydraulics (optional, provisional)
                      ↓
              exposure / asset query
                      ↓
         chain uncertainty + provenance
```

| Concept | Not the same as |
|---------|-----------------|
| Rainfall susceptibility | Flood depth |
| Delta-change climate | Dynamical downscaling |
| Statistical return level | Guaranteed observed event |
| RainfallForcing | Hydraulic depth |
| Physical exposure | Financial risk |

---

## Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Authoritative config: `config/rozvi.yaml`

---

## Run

```bash
# CLI
python main.py --point 31.05,-17.83 --crs EPSG:4326 --buffer-km 25 \
  --start-date 2019-01-01 --end-date 2019-12-31 --mode local

# EPRF local precip cube
python run_eprf.py --config config/eprf/eprf_config.yaml \
  --local-precip data/raw/daily_precip.npy --output-dir outputs/eprf

# Phase 8 end-to-end demonstration (synthetic AMS + toy DEM)
python examples/workflow_phase8_end_to_end.py
```

---

## Tests

```bash
PYTHONPATH=. python -m pytest tests/ -q
```

---

## Version

| Component | Version |
|-----------|---------|
| ROZVI | **0.10.0** |
| EPRF | **8.2.0** |

Phases completed: foundation (2), scientific core (3), hydrology (4), hydraulics (5), risk/assets (6), chain uncertainty (7), platform hardening (8).

---

## Limitations

See [docs/SCIENTIFIC_CLAIMS.md](docs/SCIENTIFIC_CLAIMS.md) and [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md).

Flood depth products are **provisional**. Bundled precip records may be short. Do not present susceptibility as flood hazard or delta-change as dynamical downscaling.

---

## Scientific API (Phase 9)

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000
# GET  /v1/rozvi/info
# GET  /v1/rozvi/capabilities
# POST /v1/rozvi/return-periods
# POST /v1/rozvi/event-hydrology
# POST /v1/rozvi/chain
```

Verification:

```bash
bash scripts/verify.sh
```
