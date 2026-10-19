# Phase 8 — Platform hardening & scientific honesty

**Date:** 2026-10-09  
**Platform:** ROZVI **0.7.0**  
**EPRF:** 8.2.0

---

## Objectives

1. Publish an authoritative **capability matrix** (IMPLEMENTED / VALIDATED / PROVISIONAL / NOT YET IMPLEMENTED).
2. Publish a binding **scientific claims** statement.
3. Provide an **end-to-end demonstration** that wires rainfall → hydrology → provisional hydraulics → exposure → chain uncertainty without over-claiming skill.
4. Align README language with Phases 2–8.

---

## Deliverables

| Item | Path |
|------|------|
| Capability matrix | `docs/CAPABILITY_MATRIX.md` |
| Scientific claims | `docs/SCIENTIFIC_CLAIMS.md` |
| E2E demo | `examples/workflow_phase8_end_to_end.py` |
| This report | `docs/PHASE8_PLATFORM_HARDENING_REPORT.md` |

No new unvalidated scientific methods were introduced. Phase 8 consolidates honesty and operability of what already exists.

---

## Demo behaviour

The Phase 8 workflow:

- Uses **synthetic** annual maxima (labelled as such)
- Runs GEV return periods with bootstrap and confidence labels
- Builds `RainfallForcing` (rainfall ≠ depth)
- Runs SCS-CN event hydrology
- Optionally runs a **toy-DEM** hydraulic smoke case → **provisional** depth
- Samples assets and builds a risk snapshot with disclaimers
- Builds **weakest-link** chain uncertainty and provenance JSON

Overall chain confidence is expected to be **Very low** when hydraulics are provisional.

---

## Explicit non-claims

Unchanged from Phases 5–7: no event-validated flood maps, no financial loss, no dynamical downscaling, no calibrated depth predictive interval without a user-asserted ensemble.

---

## Version

ROZVI **0.7.0**
