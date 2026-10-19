# Phase 4 — Hydrology Implementation Report

**Date:** 2026-10-09  
**Platform:** ROZVI **0.3.0**  
**EPRF engine:** 8.2.0  

---

## Objective

Separate **hydrology** from **hydraulics**:

```
rainfall → losses / infiltration → excess rainfall → hydrograph → (hydraulics)
```

Do not claim flood depth from CN or unit hydrographs alone.

---

## Implemented

### Package `src/hydrology/`

| Module | Contents |
|--------|----------|
| `losses.py` | SCS Curve Number excess; simplified Green–Ampt; `LossMethod` enum |
| `hydrograph.py` | `Hydrograph` Q(t); triangular UH; convolution; rational peak (screening) |
| `pipeline.py` | `run_event_hydrology` end-to-end event runner + hydraulic forcing payload |
| `validate_discharge.py` | Compare simulated vs observed hydrographs when data exist |

### Integration

- `src/hydraulics/multi_peril.py` now **imports** `Hydrograph` from `src.hydrology` (fallback class retained if import fails).
- Hydraulics package still owns 2D SWE routing; pluvial CN/GA inside the solver time loop remains for grid-cell forcing but the **canonical event hydrology API** is `src.hydrology`.

### Config (`config/rozvi.yaml`)

Expanded `hydrology:` block: CN, Ia ratio, Green–Ampt parameters, UH notes, discharge validation flag.

---

## Tests

`tests/hydrology/test_hydrology.py` — **10 passed**

- CN: excess < precip; higher CN → more excess  
- Green–Ampt mass balance  
- UH non-negative; hydrograph peak/volume > 0  
- Event pipeline produces hydraulic forcing series  
- Perfect-match discharge validation  
- Hydraulics imports shared Hydrograph  

---

## Scientific limits (explicit)

| Topic | Status |
|-------|--------|
| SCS CN / triangular UH | Implemented; regional calibration **not** claimed |
| Green–Ampt | Simplified; needs soil parameters |
| Continuous simulation | Not implemented |
| Observed discharge calibration | Hook only — **NOT VALIDATED** without user Q(t) |
| Flood depth | Still requires hydraulics module |

---

## Example

```python
from src.hydrology import run_event_hydrology, LossMethod
import numpy as np

hyetograph_mm = np.array([2, 5, 12, 20, 15, 8, 3], dtype=float)
result = run_event_hydrology(
    hyetograph_mm,
    area_km2=40.0,
    loss_method=LossMethod.CURVE_NUMBER,
    curve_number=78.0,
    dt_h=1.0,
)
print(result.peak_m3s, result.excess_total_mm)
forcing = result.to_hydraulic_forcing_series()  # for fluvial/pluvial coupling
```

---

## Version

ROZVI **0.3.0**

Next: **Phase 5** — hydraulics validation smoke tests and clearer provisional labelling of depth products.
