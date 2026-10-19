# EPRF v7.0 Methodology

## 1. Problem definition

Estimate, for any spatial domain with a daily precipitation record:

1. Where extreme rainfall is historically most intense (characterisation).
2. How intense rainfall of given rarity is expected to be (return levels).
3. How uncertain those estimates are (bootstrap CIs + quality flags).
4. How the extremes may change under transparent climate delta-change assumptions.

## 2. Why the original weighted-overlay susceptibility score is retained only as a diagnostic

The original model’s primary product was \(S = \sum w_i X_i\). When \(X_i\) included MAP and Rx indices derived from the same precipitation field, the score became circular. In v7 those indices are **outputs**, not predictors. A non-circular susceptibility diagnostic may still be produced from independent atmospheric and terrain predictors if a user explicitly requests it.

## 3. Extreme-value model

- **Block maxima**: annual maximum series extracted from daily data (minimum 50 % valid days per year).
- **Distribution**: Generalized Extreme Value (GEV) fitted by maximum likelihood; Gumbel MOM fallback for short records.
- **Return levels**: quantiles at T = 2, 5, 10, 20, 25, 50, 100, 200, 500 years.
- **Uncertainty**: parametric bootstrap (default 200 resamples) → central, lower and upper CI layers.
- **Optional POT/GPD**: available for users who prefer peaks-over-threshold with declustering.

Assumptions and limitations are written into every `provenance.json`.

## 4. Validation

- Continuous metrics: MAE, RMSE, bias, correlation, R², NSE, KGE.
- Extreme-event metrics: POD, FAR, CSI, frequency bias, RMSE on extremes.
- Spatial block CV (KMeans) and blocked temporal CV to limit leakage.

## 5. Climate change

Transparent delta-change (or user-supplied ensemble tables). No claim of dynamical downscaling. Non-stationary GEV is a documented future extension.

## 6. Reproducibility

- Fixed random seeds.
- Configuration file versioned with the run.
- Automatic provenance JSON.
- Unit and integration tests under `tests/eprf/`.

## 7. What the model can and cannot claim

**Can claim**  
- Statistically defensible return levels with quantified uncertainty for the supplied precipitation record.
- Transparent diagnostic indices (ETCCDI).
- Clear data-quality flags based on record length (and optional station density).

**Cannot claim**  
- Short-range weather forecast skill.
- Flood inundation (use the separate hydraulics module).
- Global superiority without independent multi-region validation.
- High confidence for return periods much longer than the observational record.

---

*Version 7.0.0 — Extreme Precipitation Risk Framework*
