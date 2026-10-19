# Scientific Audit — Heavy Rainfall Model (Original → v7.0)

**Audit date:** 2026-10-07  
**Original version examined:** 2.1 / 4.0 (mixed versioning in config/README)  
**Upgraded version:** 7.0.0 — Extreme Precipitation Risk Framework (EPRF)

---

## 1. Executive summary of the original system

The original repository implements a **relative heavy-rainfall susceptibility** model based on a transparent weighted linear combination of standardized factor layers:

\[
S(p) = \sum_i w_i X_i(p), \quad \sum w_i = 1
\]

Weights are obtained either by Analytic Hierarchy Process (AHP / Saaty) or by Random-Forest permutation importance. Supporting modules provide ETCCDI rainfall indices, basic Gumbel/GEV return periods, Monte-Carlo weight uncertainty, a simple CMIP6 delta-change table, an optional supervised ML predictor with spatial KMeans folds, and a separate 2-D shallow-water flood module.

**Critical scientific statement (original):**  
The primary deliverable is a **relative ranking**, not a quantitative rainfall intensity (mm), frequency (events yr⁻¹), or return level (mm for T-year event). The README correctly labels this distinction; the code largely enforces it. However, several design choices undermine statistical validity and physical interpretability for operational climate-risk use.

---

## 2. Scientific validity (A)

### Supported / retainable elements
- Explicit separation of susceptibility vs. quantitative prediction.
- Exclusion of pure flood-runoff factors (TWI, LULC, soil moisture, NDVI) from the rainfall score.
- ETCCDI index definitions (Rx1day, Rx5day, R95p, R10mm, CDD, CWD).
- AHP consistency-ratio check (CR ≤ 0.10).
- Collinearity diagnostics (Pearson, Spearman, VIF) with logging rather than silent dropping.
- Spatial KMeans-based CV folds (avoids naïve random pixel split).
- Resolution guidance (do not claim 30 m rainfall information from CHIRPS/ERA5).

### Unsupported or weak assumptions
1. **Circularity / target leakage in the susceptibility score.**  
   Mean annual precipitation, Rx1day, Rx5day and R95p are derived from the same precipitation field that the model is trying to characterise. Including them as “predictors” with non-zero weights produces a near-tautological ranking (“places that already have high extreme indices receive high susceptibility”). This inflates apparent skill and violates the principle that predictors should be independent of the quantity being ranked.

2. **Arbitrary expert weights without regional calibration.**  
   Default AHP pairwise matrix is hard-coded; no evidence is provided that the relative importance of humidity vs. elevation is appropriate for Zimbabwe (or any other domain).

3. **Orographic enhancement treated as static aspect exposure.**  
   A single dominant wind direction (default 90°) is used. Real orographic precipitation depends on wind direction at the time of the event, atmospheric stability, and moisture flux; a static layer is only a weak proxy.

4. **Seasonality configuration is incorrect for Zimbabwe.**  
   Config lists wet season as months [3,4,5,10,11,12]. In Zimbabwe the primary rainy season is November–March (with a secondary peak possible in some northern areas). Dry-season months are largely May–September.

5. **Synthetic demonstration data.**  
   Bundled rasters and station file contain synthetic values and an invalid projected study-area geometry (y-coordinates ~ –300 000). This is acceptable for unit tests but must never be presented as a calibrated Zimbabwe product.

6. **Missing physically relevant drivers for tropical/subtropical convection.**  
   No precipitable water, CAPE/CIN, mid-level moisture, low-level convergence, or large-scale indices (ENSO, IOD, MJO) are present, even though these dominate extreme rainfall variability in southern Africa.

### Data leakage risks
- When MAP/Rx indices are used both to define the target and as features, any validation that samples from the same period/region is contaminated.
- Station file mixes “station”, “CHIRPS” and “ERA5-Land” sources without clear observation vs. estimate distinction.

---

## 3. Statistical validity (B)

| Aspect | Original status | Assessment |
|--------|-----------------|------------|
| Extreme-value model | Block maxima → Gumbel or GEV | Acceptable starting point; no Peak-over-Threshold, no non-stationarity, limited return-level uncertainty |
| Return periods | 10, 50, 100, 250, 500 yr | Standard; confidence intervals incomplete |
| Bias correction | Absent | Critical gap for multi-source merging |
| Spatial autocorrelation | Diagnosed via correlation matrix; CV uses spatial folds | Good intent; not fully propagated into prediction intervals |
| Temporal non-stationarity | Not modelled | Important for climate-change applications |
| Zero-inflation / dry days | Handled only via ETCCDI wet-day threshold | Adequate for indices; insufficient for intensity-duration modelling |
| Calibration / coverage | Minimal | No systematic quantile coverage or reliability diagrams |
| Cross-validation | Spatial KMeans + optional leave-one-out style | Correct direction; needs blocked temporal CV as well |

---

## 4. Geospatial validity (C)

- CRS handling is present (EPSG:4326 + metric CRS).
- Target resolution correctly defaults to ~5 km (CHIRPS scale).
- Raster alignment QC exists.
- Study-area GeoJSON is geometrically invalid for real geographic use.
- Station density and representativeness are not quantified.
- Edge effects and AOI buffer are not systematically treated.

---

## 5. Climate-science validity (D)

Relevant mechanisms for Zimbabwe / southern Africa:
- Moisture flux from the Indian Ocean and Congo basin.
- Tropical temperate troughs, cut-off lows, and mesoscale convective systems.
- Orographic enhancement over the Eastern Highlands.
- ENSO (El Niño → drought tendency; La Niña → wetter) and IOD modulation.
- Strong seasonality (Nov–Mar).

Original model captures only a static subset of orographic and mean atmospheric fields. It does not represent large-scale circulation variability or convective potential.

---

## 6. Benchmarking against international practice (Phase 2)

| Institution / literature | Relevant practice | Original model | v7 target |
|--------------------------|-------------------|----------------|-----------|
| ETCCDI / WMO | Standard extreme indices | Implemented | Retain + expand |
| IPCC / CMIP6 | Non-stationary extremes, SSP scenarios | Simple fixed % deltas | Ensemble delta + optional non-stationary GEV |
| ECMWF / Copernicus | Multi-source precipitation (ERA5, IMERG, gauge) | CHIRPS primary + ERA5 option | Explicit multi-source catalogue + bias-correction interface |
| NOAA / Atlas 14 style | Regional frequency analysis, L-moments, spatial pooling | Pixel-wise GEV | Pixel-wise GEV + bootstrap CI; spatial pooling optional later |
| CHIRPS / IMERG literature | Gauge–satellite merging, quantile mapping | Absent | Interface + empirical quantile mapping module |
| Spatial extremes literature | Max-stable processes, conditional extremes | Absent | Documented future work; start with independent-pixel GEV |
| ML downscaling literature | Quantile regression forests, CNNs with proper CV | Basic RF/GBM | Optional QRF with spatial+temporal blocked CV |

---

## 7. Decision: what is retained, improved, replaced or removed

| Component | Decision | Rationale |
|-----------|----------|-----------|
| Weighted-overlay susceptibility | **Retain as one diagnostic product** | Transparent, useful for communication; must not be the sole claim |
| MAP / Rx indices as predictors of susceptibility | **Remove from predictor set** | Circular |
| AHP weighting | **Retain with mandatory regional review flag** | Expert knowledge still valuable when CR is acceptable |
| Data-driven weights (RF importance) | **Retain** | Empirical alternative |
| ETCCDI indices | **Retain & expand** | Community standard |
| Gumbel/GEV return levels | **Upgrade** to full GEV + bootstrap CIs + POT option | Statistical defensible extremes |
| Monte-Carlo weight uncertainty | **Retain & expand** to prediction intervals | Good start |
| Simple CMIP6 % deltas | **Upgrade** to configurable ensemble tables + clear projection language | Avoid over-claiming |
| Hydraulics 2-D solver | **Keep as separate module** | Outside core rainfall science |
| Synthetic data pathway | **Keep only for unit tests** | Production path requires real or user-supplied data |
| Station validation | **Strengthen** | Separate observation vs. estimate sources |

---

## 8. Honest limitations of the upgraded model (preview)

Even after upgrade, the framework:
- Is **not** a numerical weather prediction system.
- Does **not** claim skilful short-range forecasts.
- Relies on the quality and density of input precipitation products and gauges.
- Pixel-wise GEV assumes spatial independence of extremes (conservative for uncertainty; underestimates spatial coherence of events).
- Climate projections remain delta-change / scaled extremes; full dynamical downscaling is out of scope.
- Transferability to other African countries requires local gauge calibration and re-evaluation of orographic / moisture predictors.

---

*End of audit summary. Full methodology, architecture and implementation follow in accompanying documents and code.*
