# Changelog — EPRF v7.0.0

## Added
- `src/eprf/` package: Extreme Precipitation Risk Framework
  - `extremes/gev.py` — GEV annual-maxima fitting + parametric bootstrap CIs
  - `extremes/pot.py` — Peaks-over-Threshold / GPD with declustering
  - `features/indices.py` — clean ETCCDI indices (diagnostic only)
  - `validation/metrics.py` — MAE, RMSE, bias, corr, R², NSE, KGE, POD, FAR, CSI
  - `validation/crossval.py` — blocked temporal + spatial hold-out
  - `uncertainty/quality.py` — transparent confidence flags based on record length
  - `uncertainty/bootstrap.py` — public bootstrap API
  - `pipeline.py` — end-to-end reproducible pipeline with provenance
- `config/eprf/eprf_config.yaml` — versioned configuration
- `run_eprf.py` — CLI entry point
- `docs/SCIENTIFIC_AUDIT_v7.md` — full scientific audit of the original model
- `docs/METHODOLOGY_v7.md` — methodology and claims
- `tests/eprf/` — unit tests (6 tests, all passing)

## Changed (scientific)
- **Removed circularity**: MAP, Rx1day, Rx5day, R95p are no longer used as predictors of susceptibility; they are diagnostic outputs only.
- **Corrected Zimbabwe seasonality**: wet season set to Nov–Mar.
- **Return levels** now carry explicit bootstrap confidence intervals and quality flags.
- **Honest claims**: every run writes a provenance statement of what the numbers do and do not mean.
- Primary quantitative product is now GEV return levels (mm), not a relative susceptibility score.

## Retained from original
- Transparent weighted-overlay susceptibility as an *optional diagnostic* (non-circular predictors only).
- AHP + data-driven weighting utilities.
- Collinearity diagnostics (Pearson / Spearman / VIF).
- Spatial KMeans CV folds.
- Hydraulics module (unchanged, separate concern).
- Remote data acquisition interfaces (CHIRPS / ERA5 / DEM).

## Known limitations (explicit)
- Bundled daily_precip.npy contains only ~3 years → quality flags correctly set to “Very low”; 100-year return levels are not reported as reliable.
- Pixel-wise GEV ignores spatial dependence of extremes.
- Climate module remains transparent delta-change (no dynamical downscaling).
- Full multi-source gauge–satellite merging and bias correction interfaces are designed but require user-supplied gauge data to exercise.

## Version statement
**EPRF v7.0.0** is a statistically defensible extreme-precipitation characterisation and return-level framework. It is not a numerical weather prediction system and does not claim flood inundation skill.
