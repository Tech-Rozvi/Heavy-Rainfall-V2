# Phase 9 — Operational API & verification harness

**Date:** 2026-10-09  
**Platform:** ROZVI **0.8.0**

---

## Objectives

1. Expose scientifically supported ROZVI capabilities through stable HTTP routes.
2. Provide a one-command verification script for tests + demo + API import.
3. Keep flood-depth generation off the generic API unless a full hydraulics run is performed (still provisional).

---

## API routes (`api/rozvi_routes.py`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1/rozvi/info` | Platform version + honesty notes |
| GET | `/v1/rozvi/capabilities` | Machine-readable status map |
| POST | `/v1/rozvi/return-periods` | GEV return levels from annual maxima |
| POST | `/v1/rozvi/event-hydrology` | CN event hydrology summary |
| POST | `/v1/rozvi/chain` | Weakest-link chain uncertainty |

All result payloads that could be misread include a **disclaimer**.

`GET /health` now reports ROZVI platform version.

---

## Verification

```bash
bash scripts/verify.sh
```

Runs: version print → unit tests → Phase 8 e2e demo → API route import check.

---

## Tests

`tests/api/test_rozvi_routes.py` — FastAPI TestClient.

---

## Explicit non-claims

- No `POST /flood-depth` that invents inundation from rainfall alone.
- No financial risk endpoints.
- Return-period and hydrology endpoints are statistical / conceptual model products, not regulatory design floods.

---

## Version

ROZVI **0.8.0**
