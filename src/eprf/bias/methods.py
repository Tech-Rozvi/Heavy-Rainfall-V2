"""
Bias-correction methods for gridded / satellite rainfall vs gauges.

Scientific notes
----------------
- Methods are fit on a *calibration* sample and applied to a *target* sample.
  Callers must enforce temporal hold-out to avoid leakage.
- Zero-inflated daily rainfall: wet-day threshold (default 0.1 mm) is applied
  before distributional mapping of positive amounts where relevant.
- No method is assumed best a priori; use ``benchmark_bias_methods``.

References (method families, not code copies):
- Linear / variance scaling: common in hydroclimate bias-correction literature
- Empirical quantile mapping (EQM): Themeßl et al. style rank mapping
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

WET_DAY_MM = 0.1


@dataclass
class BiasCorrectionResult:
    """Corrected series plus fit diagnostics (never silent)."""
    method: str
    corrected: np.ndarray
    parameters: dict = field(default_factory=dict)
    n_cal: int = 0
    wet_day_threshold_mm: float = WET_DAY_MM
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["corrected"] = "array"  # do not dump full arrays into JSON by default
        return d


def _finite_pair(obs: np.ndarray, mod: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    o = np.asarray(obs, dtype="float64").ravel()
    m = np.asarray(mod, dtype="float64").ravel()
    mask = np.isfinite(o) & np.isfinite(m)
    return o[mask], m[mask]


def linear_scaling(
    model: np.ndarray,
    obs_cal: np.ndarray,
    mod_cal: np.ndarray,
    *,
    wet_day_mm: float = WET_DAY_MM,
) -> BiasCorrectionResult:
    """
    Multiplicative scaling so mean(model) matches mean(obs) on calibration.

    factor = mean(obs_cal) / mean(mod_cal)
    corrected = model * factor
    """
    o, m = _finite_pair(obs_cal, mod_cal)
    notes = []
    if len(o) < 10:
        notes.append("Fewer than 10 paired calibration points; factor unreliable.")
    mean_o = float(np.mean(o)) if len(o) else 0.0
    mean_m = float(np.mean(m)) if len(m) else 0.0
    if mean_m <= 1e-12:
        factor = 1.0
        notes.append("Calibration model mean ~0; factor set to 1.0")
    else:
        factor = mean_o / mean_m
    corrected = np.asarray(model, dtype="float64") * factor
    corrected = np.where(np.isfinite(corrected), np.maximum(corrected, 0.0), corrected)
    return BiasCorrectionResult(
        method="linear_scaling",
        corrected=corrected,
        parameters={"factor": factor, "mean_obs_cal": mean_o, "mean_mod_cal": mean_m},
        n_cal=len(o),
        wet_day_threshold_mm=wet_day_mm,
        notes=notes,
    )


def variance_scaling(
    model: np.ndarray,
    obs_cal: np.ndarray,
    mod_cal: np.ndarray,
    *,
    wet_day_mm: float = WET_DAY_MM,
) -> BiasCorrectionResult:
    """
    Match mean and variance of calibration observations.

    corrected = mean_o + (model - mean_m) * (std_o / std_m)
    Rainfall clipped at 0.
    """
    o, m = _finite_pair(obs_cal, mod_cal)
    notes = []
    if len(o) < 10:
        notes.append("Fewer than 10 paired calibration points; scaling unreliable.")
    mean_o, mean_m = float(np.mean(o)), float(np.mean(m))
    std_o = float(np.std(o, ddof=1)) if len(o) > 1 else 0.0
    std_m = float(np.std(m, ddof=1)) if len(m) > 1 else 0.0
    if std_m <= 1e-12:
        scale = 1.0
        notes.append("Calibration model std ~0; variance scale set to 1.0")
    else:
        scale = std_o / std_m
    x = np.asarray(model, dtype="float64")
    corrected = mean_o + (x - mean_m) * scale
    corrected = np.where(np.isfinite(corrected), np.maximum(corrected, 0.0), corrected)
    return BiasCorrectionResult(
        method="variance_scaling",
        corrected=corrected,
        parameters={
            "mean_obs": mean_o, "mean_mod": mean_m,
            "std_obs": std_o, "std_mod": std_m, "scale": scale,
        },
        n_cal=len(o),
        wet_day_threshold_mm=wet_day_mm,
        notes=notes,
    )


def empirical_quantile_mapping(
    model: np.ndarray,
    obs_cal: np.ndarray,
    mod_cal: np.ndarray,
    *,
    n_quantiles: int = 100,
    wet_day_mm: float = WET_DAY_MM,
) -> BiasCorrectionResult:
    """
    Empirical quantile mapping (EQM) on the full distribution including zeros.

    For each model value, find its percentile in mod_cal and replace with the
    corresponding percentile of obs_cal.  Extrapolation uses end quantiles.
    """
    o, m = _finite_pair(obs_cal, mod_cal)
    notes = []
    if len(o) < 20:
        notes.append("Fewer than 20 paired points; EQM quantiles unstable.")
    if len(o) < 5:
        # Fall back to linear scaling
        fb = linear_scaling(model, obs_cal, mod_cal, wet_day_mm=wet_day_mm)
        fb.notes.append("EQM fell back to linear_scaling due to insufficient calibration data.")
        fb.method = "empirical_quantile_mapping->linear_scaling"
        return fb

    nq = min(n_quantiles, max(len(o) // 2, 5))
    probs = np.linspace(0.0, 1.0, nq)
    mod_q = np.quantile(m, probs)
    obs_q = np.quantile(o, probs)
    # Ensure strictly increasing for interpolation
    mod_q = _make_strictly_increasing(mod_q)
    x = np.asarray(model, dtype="float64")
    flat = x.ravel()
    out = np.full_like(flat, np.nan)
    finite = np.isfinite(flat)
    out[finite] = np.interp(flat[finite], mod_q, obs_q, left=obs_q[0], right=obs_q[-1])
    out = np.maximum(out, 0.0)
    corrected = out.reshape(x.shape)
    return BiasCorrectionResult(
        method="empirical_quantile_mapping",
        corrected=corrected,
        parameters={"n_quantiles": nq},
        n_cal=len(o),
        wet_day_threshold_mm=wet_day_mm,
        notes=notes,
    )


def quantile_mapping(
    model: np.ndarray,
    obs_cal: np.ndarray,
    mod_cal: np.ndarray,
    *,
    wet_day_mm: float = WET_DAY_MM,
) -> BiasCorrectionResult:
    """Alias for empirical_quantile_mapping (default distributional method)."""
    return empirical_quantile_mapping(
        model, obs_cal, mod_cal, wet_day_mm=wet_day_mm,
    )


def _make_strictly_increasing(q: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    out = np.array(q, dtype="float64", copy=True)
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + eps
    return out
