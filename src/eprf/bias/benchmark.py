"""
Benchmark bias-correction methods under temporal hold-out.

Avoids leakage: calibration on the first fraction of the paired series,
evaluation on the held-out tail (or user-supplied indices).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Callable, Optional

import numpy as np

from src.eprf.bias.methods import (
    linear_scaling,
    variance_scaling,
    empirical_quantile_mapping,
    BiasCorrectionResult,
)
from src.eprf.validation.metrics import evaluate_precipitation, evaluate_extremes
from src.utils import get_logger

logger = get_logger(__name__)


METHODS: dict[str, Callable] = {
    "linear_scaling": linear_scaling,
    "variance_scaling": variance_scaling,
    "empirical_quantile_mapping": empirical_quantile_mapping,
}


@dataclass
class BiasBenchmarkRow:
    method: str
    n_cal: int
    n_val: int
    mae: float
    rmse: float
    bias: float
    corr: float
    mae_raw: float
    rmse_raw: float
    bias_raw: float
    improvement_rmse_pct: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BiasBenchmarkTable:
    rows: list[BiasBenchmarkRow]
    best_method_by_rmse: Optional[str]
    holdout_fraction: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rows": [r.to_dict() for r in self.rows],
            "best_method_by_rmse": self.best_method_by_rmse,
            "holdout_fraction": self.holdout_fraction,
            "notes": self.notes,
        }

    def summary_text(self) -> str:
        lines = [
            f"{'Method':<30} {'RMSE':>8} {'MAE':>8} {'Bias':>8} {'Corr':>7} {'ΔRMSE%':>8}"
        ]
        lines.append("-" * 75)
        for r in self.rows:
            lines.append(
                f"{r.method:<30} {r.rmse:8.3f} {r.mae:8.3f} {r.bias:8.3f} "
                f"{r.corr:7.3f} {r.improvement_rmse_pct:8.1f}"
            )
        lines.append(f"Best by RMSE: {self.best_method_by_rmse}")
        return "\n".join(lines)


def benchmark_bias_methods(
    obs: np.ndarray,
    model: np.ndarray,
    *,
    holdout_fraction: float = 0.3,
    methods: Optional[list[str]] = None,
    random_seed: Optional[int] = None,
) -> BiasBenchmarkTable:
    """
    Compare bias-correction methods with temporal hold-out.

    Parameters
    ----------
    obs, model : paired 1-D series (same length after alignment)
    holdout_fraction : last fraction reserved for validation
    methods : subset of METHODS keys; default all
    random_seed : unused for temporal split (kept for API stability)

    Returns
    -------
    BiasBenchmarkTable with metrics on the validation segment only.
    """
    o = np.asarray(obs, dtype="float64").ravel()
    m = np.asarray(model, dtype="float64").ravel()
    n = min(len(o), len(m))
    o, m = o[:n], m[:n]
    mask = np.isfinite(o) & np.isfinite(m)
    o, m = o[mask], m[mask]
    notes = []
    if len(o) < 30:
        notes.append(
            f"Only {len(o)} paired finite points; benchmark is indicative only."
        )

    n_val = max(1, int(round(len(o) * holdout_fraction)))
    n_cal = len(o) - n_val
    if n_cal < 10:
        n_cal = max(10, len(o) // 2)
        n_val = len(o) - n_cal
    o_cal, m_cal = o[:n_cal], m[:n_cal]
    o_val, m_val = o[n_cal:], m[n_cal:]

    raw = evaluate_precipitation(o_val, m_val)
    method_names = methods or list(METHODS.keys())
    rows: list[BiasBenchmarkRow] = []

    for name in method_names:
        fn = METHODS.get(name)
        if fn is None:
            notes.append(f"Unknown method skipped: {name}")
            continue
        result: BiasCorrectionResult = fn(m_val, o_cal, m_cal)
        metrics = evaluate_precipitation(o_val, result.corrected)
        rmse_raw = raw.get("rmse") or np.nan
        rmse = metrics.get("rmse") or np.nan
        if np.isfinite(rmse_raw) and rmse_raw > 0 and np.isfinite(rmse):
            improv = 100.0 * (rmse_raw - rmse) / rmse_raw
        else:
            improv = float("nan")
        rows.append(BiasBenchmarkRow(
            method=result.method,
            n_cal=result.n_cal,
            n_val=len(o_val),
            mae=float(metrics.get("mae") or np.nan),
            rmse=float(rmse) if np.isfinite(rmse) else float("nan"),
            bias=float(metrics.get("bias") or np.nan),
            corr=float(metrics.get("corr") or np.nan) if metrics.get("corr") is not None else float("nan"),
            mae_raw=float(raw.get("mae") or np.nan),
            rmse_raw=float(rmse_raw) if np.isfinite(rmse_raw) else float("nan"),
            bias_raw=float(raw.get("bias") or np.nan),
            improvement_rmse_pct=float(improv) if np.isfinite(improv) else float("nan"),
            notes=list(result.notes),
        ))

    # Best = lowest validation RMSE among finite scores
    finite = [r for r in rows if np.isfinite(r.rmse)]
    best = min(finite, key=lambda r: r.rmse).method if finite else None

    table = BiasBenchmarkTable(
        rows=rows,
        best_method_by_rmse=best,
        holdout_fraction=holdout_fraction,
        notes=notes,
    )
    logger.info("Bias benchmark complete; best=%s", best)
    return table
