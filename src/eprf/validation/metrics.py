"""
Validation metrics for precipitation intensity and extremes.

All metrics are computed only on finite paired observations.
Extreme-event detection uses a configurable threshold (default 95th percentile
of the observed series or a fixed mm value).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)


def _finite_pair(obs: np.ndarray, sim: np.ndarray):
    o = np.asarray(obs, dtype="float64").ravel()
    s = np.asarray(sim, dtype="float64").ravel()
    mask = np.isfinite(o) & np.isfinite(s)
    return o[mask], s[mask]


def evaluate_precipitation(obs: np.ndarray, sim: np.ndarray) -> dict[str, float]:
    """Standard continuous metrics."""
    o, s = _finite_pair(obs, sim)
    if len(o) < 3:
        return {k: np.nan for k in ("n", "mae", "rmse", "bias", "corr", "r2", "nse", "kge")}

    err = s - o
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    bias = float(np.mean(err))
    if np.std(o) < 1e-12 or np.std(s) < 1e-12:
        corr = np.nan
    else:
        corr = float(np.corrcoef(o, s)[0, 1])
    ss_res = np.sum(err ** 2)
    ss_tot = np.sum((o - np.mean(o)) ** 2)
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan
    # NSE
    nse = r2  # same formula
    # KGE (Gupta et al. 2009)
    r = corr if np.isfinite(corr) else 0.0
    alpha = float(np.std(s) / np.std(o)) if np.std(o) > 0 else np.nan
    beta = float(np.mean(s) / np.mean(o)) if np.mean(o) != 0 else np.nan
    kge = float(1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)) if np.isfinite(alpha) else np.nan

    return {
        "n": int(len(o)),
        "mae": mae,
        "rmse": rmse,
        "bias": bias,
        "corr": corr,
        "r2": r2,
        "nse": nse,
        "kge": kge,
    }


def evaluate_extremes(
    obs: np.ndarray,
    sim: np.ndarray,
    threshold: Optional[float] = None,
    obs_percentile: float = 95.0,
) -> dict[str, float]:
    """
    Binary extreme-event detection metrics + intensity error on extremes.
    """
    o, s = _finite_pair(obs, sim)
    if len(o) < 10:
        return {k: np.nan for k in ("pod", "far", "csi", "bias_freq", "rmse_extreme", "n_extreme_obs")}

    if threshold is None:
        threshold = float(np.percentile(o, obs_percentile))

    o_ext = o >= threshold
    s_ext = s >= threshold
    hits = np.sum(o_ext & s_ext)
    misses = np.sum(o_ext & ~s_ext)
    false_alarms = np.sum(~o_ext & s_ext)

    pod = hits / (hits + misses) if (hits + misses) > 0 else np.nan
    far = false_alarms / (hits + false_alarms) if (hits + false_alarms) > 0 else np.nan
    csi = hits / (hits + misses + false_alarms) if (hits + misses + false_alarms) > 0 else np.nan
    bias_freq = (hits + false_alarms) / (hits + misses) if (hits + misses) > 0 else np.nan

    # Intensity error on observed extremes
    if hits + misses > 0:
        rmse_ext = float(np.sqrt(np.mean((s[o_ext] - o[o_ext]) ** 2)))
    else:
        rmse_ext = np.nan

    return {
        "threshold": threshold,
        "pod": float(pod) if np.isfinite(pod) else np.nan,
        "far": float(far) if np.isfinite(far) else np.nan,
        "csi": float(csi) if np.isfinite(csi) else np.nan,
        "bias_freq": float(bias_freq) if np.isfinite(bias_freq) else np.nan,
        "rmse_extreme": rmse_ext,
        "n_extreme_obs": int(np.sum(o_ext)),
    }


def spatial_block_cv_indices(
    ny: int,
    nx: int,
    n_blocks: int = 5,
    random_seed: int = 42,
) -> np.ndarray:
    """
    Assign each pixel to a spatial block via KMeans on coordinates.
    Returns fold_id array of shape (ny, nx).
    """
    from sklearn.cluster import KMeans
    rows, cols = np.indices((ny, nx))
    coords = np.column_stack([rows.ravel(), cols.ravel()])
    km = KMeans(n_clusters=n_blocks, random_state=random_seed, n_init=10)
    labels = km.fit_predict(coords)
    return labels.reshape(ny, nx)
