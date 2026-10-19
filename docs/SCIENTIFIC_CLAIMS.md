# ROZVI Scientific Claims Statement

**Version:** ROZVI 0.7.0 · EPRF 8.2.0

This statement defines what ROZVI **may** claim and what it **must not** claim.
It is binding for reports, APIs, and user-facing products built on this codebase.

---

## The model **can** claim

1. **AOI and point geometry** can be ingested with explicit CRS confidence diagnostics.
2. **ETCCDI-style indices** can be computed from a supplied daily precipitation series.
3. **GEV return levels** can be estimated with bootstrap intervals, record length, and
   extrapolation flags when the return period exceeds the observational record.
4. **Design storms** can be generated from a return level and a temporal pattern, and
   packaged as `RainfallForcing` for a separate hydraulics module.
5. **Climate delta factors** can adjust design rainfall under named SSP/horizon
   assumptions when factors are supplied or transparently defaulted (if allowed).
6. **Event hydrology** (SCS-CN / simplified Green–Ampt + triangular UH) can produce
   excess rainfall and a discharge hydrograph from a hyetograph and area.
7. **2D shallow-water simulation** can produce depth fields when driven by rainfall
   forcing; products are labelled **provisional** until event-validated.
8. **Physical exposure** (building counts, road length above depth thresholds) can be
   computed when assets/roads and a depth field are provided.
9. **Chain confidence** can be reported as the weakest stage; stage-level intervals
   are only shown where that stage actually computed them.

---

## The model **cannot** claim

1. That **susceptibility** or weighted-overlay scores are flood depth or inundation.
2. That **delta-change** climate adjustment is dynamical downscaling (CORDEX/WRF).
3. High confidence for **return periods much longer** than the data record.
4. **Operational forecast skill** (NWP / nowcasting).
5. **Event-validated** flood hazard maps for any domain in this repository alone.
6. **Insured loss, damage ratios, or financial risk**.
7. A **calibrated predictive interval** for flood depth without an end-to-end ensemble
   the user supplies and asserts.
8. That bundled synthetic precip or example assets represent real national archives.
9. **Regulatory design-flood** status for any output.

---

## Separation of concerns (non-negotiable)

```text
rainfall / extremes  ≠  flood depth  ≠  exposure  ≠  financial risk
statistical return level  ≠  guaranteed observed event
RainfallForcing  ≠  hydraulic simulation output
```

---

## Recommended citation language

> “ROZVI estimates extreme precipitation quantiles and optional provisional
> flood depths from user- or product-supplied data. Depth products are not
> event-validated in the public repository. Uncertainty is reported by stage;
> overall confidence follows the weakest link.”
