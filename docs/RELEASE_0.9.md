# ROZVI 0.9.0 Release Notes

**Date:** 2026-10-09  
**Codename:** Phase 10 — Release packaging & legacy quarantine

## Summary

ROZVI 0.9.0 is a packaging and honesty release. It does not introduce new
hazard physics. It makes the boundary between the **canonical** scientific
stack and the **legacy** susceptibility overlay unambiguous in code, logs,
and file metadata.

## Scientific statement (short)

ROZVI can estimate extreme precipitation quantiles with uncertainty flags,
produce design-storm rainfall forcing, run event hydrology, optionally
simulate **provisional** flood depths, and report weakest-link chain
confidence. It does **not** claim event-validated flood maps, financial loss,
or dynamical downscaling.

## Upgrade notes

- Consumers of `outputs/rasters/susceptibility.tif` should read GeoTIFF tags
  and treat the layer as a dimensionless diagnostic score only.
- Prefer `examples/workflow_phase8_end_to_end.py` and `/v1/rozvi/*` for new work.
- See `docs/SCIENTIFIC_CLAIMS.md` and `docs/CAPABILITY_MATRIX.md`.

## Verification

```bash
bash scripts/verify.sh
PYTHONPATH=. python -m pytest tests/rozvi tests/api -q
```
