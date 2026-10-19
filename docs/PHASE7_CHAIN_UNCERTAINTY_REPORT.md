# Phase 7 — Full-chain uncertainty and provenance

**Date:** 2026-10-09  
**Platform:** ROZVI **0.6.0**  
**EPRF engine:** 8.2.0

---

## Objective

Make uncertainty visible across:

```text
rainfall / extremes → bias correction → hydrology → hydraulics → exposure
```

without inventing a joint confidence interval the system did not compute.

---

## Rule

| Rule | Implementation |
|------|----------------|
| Quantitative interval only where a stage computed one | GEV CI on `rainfall_extremes`; hydrology min/max only if a sensitivity ensemble is supplied (`interval_level=None`) |
| No fabricated flood-depth CI | `hydraulics.quantified=False` unless the caller passes real ensemble samples |
| Overall confidence = weakest link | `build_chain` ordinal minimum of High > Moderate > Low > Very low |
| Full Monte Carlo through SWE | **not claimed**. `claims_full_propagation` is True only if the caller asserts samples are end-to-end realisations |
| Provenance | `provenance_for_chain` writes one record with a step per stage, config hash, and overall confidence |

---

## Module

`src/rozvi/chain.py`

- `StageUncertainty`, `ChainUncertainty`
- `stage_from_return_period`, `stage_from_bias`, `stage_from_hydrology`, `stage_from_hydraulics`, `stage_from_exposure`
- `empirical_interval`, `chain_with_ensemble`
- `provenance_for_chain`

Config (`config/rozvi.yaml`):

```yaml
uncertainty:
  combination: weakest_link
  claim_full_monte_carlo: false
  hydraulics_default_status: provisional
```

---

## Tests

`tests/rozvi/test_chain_uncertainty.py` — **10 passed**

Provisional hydraulics + exposure pull the chain to **Very low** even when the rainfall fit is only Low. That is intentional.

---

## What this does **not** claim

- A calibrated predictive interval for flood depth
- That event-validated status was checked (caller assertion; confidence capped at Moderate)
- Financial risk uncertainty (Phase 6 does not compute loss)
- Spatial correlation or non-stationary EVT

---

## Example

```python
from src.rozvi.chain import (
    build_chain, stage_from_return_period, stage_from_hydrology,
    stage_from_hydraulics, stage_from_exposure, provenance_for_chain,
)

chain = build_chain([
    stage_from_return_period(rp_result),
    stage_from_hydrology(method="curve_number", peak_m3s=peak,
                         sensitivity_peaks_m3s=[8, 12, 18]),
    stage_from_hydraulics(validation_status="provisional", max_depth_m=0.4),
    stage_from_exposure(),
])
print(chain.overall_confidence, chain.weakest_stage)
provenance_for_chain(chain, aoi_id="demo").to_json("outputs/chain_provenance.json")
```

---

## Version

ROZVI **0.6.0**
