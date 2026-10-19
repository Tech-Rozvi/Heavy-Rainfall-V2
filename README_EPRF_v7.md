# Extreme Precipitation Risk Framework (EPRF) v7.0.0

Scientifically defensible, reproducible, spatially explicit heavy-rainfall and extreme-precipitation modelling system.

## What the model can claim

- Diagnostic characterisation of historical rainfall extremes (ETCCDI indices).
- Generalized Extreme Value (GEV) return levels (mm) for configurable return periods, with parametric bootstrap confidence intervals.
- Transparent data-quality / confidence flags driven primarily by record length.
- Spatial and temporal blocked cross-validation metrics when independent observations are supplied.
- Optional non-circular susceptibility diagnostic from atmospheric and terrain predictors.

## What the model cannot claim

- Short-range numerical weather prediction skill.
- Flood depth or inundation (see the separate hydraulics module).
- High confidence for return periods much longer than the observational record.
- Dynamical downscaling of CMIP6 / CORDEX (climate module uses transparent delta-change).

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Run unit tests
python -m pytest tests/eprf/ -v

# Run on local daily precipitation cube (T, Y, X) in mm/day
python run_eprf.py --config config/eprf/eprf_config.yaml \
                   --local-precip path/to/daily_precip.npy \
                   --output-dir outputs/eprf
```

## Scientific audit and methodology

- `docs/SCIENTIFIC_AUDIT_v7.md` — rigorous audit of the original weighted-overlay model and justification for every major change.
- `docs/METHODOLOGY_v7.md` — full methodological description.
- `docs/CHANGELOG_v7.md` — list of retained, improved, replaced and removed components.

## Architecture (v7)

```
src/eprf/
  extremes/     GEV + POT extreme-value models
  features/     ETCCDI indices (diagnostic)
  validation/   metrics + blocked CV
  uncertainty/  bootstrap CIs + quality flags
  pipeline.py   end-to-end reproducible run
```

Original modules (`src/model.py`, `src/weighting.py`, hydraulics, data acquisition) remain available for the susceptibility diagnostic and flood pathway.

## Example outputs

- `eprf_indices.npz` — MAP, Rx1day, Rx5day, R95p, R10mm, CDD, CWD, …
- `eprf_return_levels.npz` — `rl_T`, `rl_T_lower`, `rl_T_upper` for each return period T
- `eprf_confidence_flags.npy` — 1–4 confidence class
- `provenance.json` — model version, parameters, scientific claims and limitations
- `summary.json` — domain-mean diagnostics

## Recommended next research steps

1. Vectorize / Dask-parallelize the per-pixel GEV fit for national-scale domains.
2. Implement empirical quantile mapping and regression-kriging gauge–satellite merging when a national gauge archive is available.
3. Add non-stationary GEV (time or covariate as location/scale driver) for climate-change attribution.
4. Spatial extremes (max-stable or conditional extremes) once multi-decadal station data exist.
5. Regional frequency analysis (L-moments, Hosking & Wallis) for data-sparse areas.
6. Full integration of ERA5 precipitable water, CAPE and large-scale indices (ENSO, IOD) as non-circular predictors.

---

**Version 7.0.0** — Extreme Precipitation Risk Framework  
Primary quantitative product: GEV return levels with uncertainty.  
Primary diagnostic product: ETCCDI indices + optional transparent susceptibility score.
