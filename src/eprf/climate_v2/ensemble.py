"""Multi-model climate ensemble utilities."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence, Union

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class ClimateEnsemble:
    """
    Container for multi-model climate deltas or fields.

    Provides ensemble mean, median, and percentiles (P10–P90).
    """
    members: dict[str, float]          # model_id -> scalar delta (or path to field)
    ssp: str
    horizon_year: int
    variable: str = "pr"
    method: str = "relative_delta"
    source: str = "user_table"

    def percentiles(self, ps: Sequence[float] = (10, 25, 50, 75, 90)) -> dict[str, float]:
        vals = np.array(list(self.members.values()), dtype="float64")
        vals = vals[np.isfinite(vals)]
        if len(vals) == 0:
            return {f"P{int(p)}": float("nan") for p in ps}
        return {f"P{int(p)}": float(np.percentile(vals, p)) for p in ps}

    def mean(self) -> float:
        vals = np.array(list(self.members.values()), dtype="float64")
        return float(np.nanmean(vals))

    def spread(self) -> float:
        vals = np.array(list(self.members.values()), dtype="float64")
        return float(np.nanstd(vals))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ssp": self.ssp,
            "horizon_year": self.horizon_year,
            "variable": self.variable,
            "method": self.method,
            "source": self.source,
            "n_members": len(self.members),
            "mean": self.mean(),
            "spread": self.spread(),
            "percentiles": self.percentiles(),
            "members": self.members,
        }


def load_ensemble_table(
    path: Union[str, Path],
    ssp: str,
    horizon_year: int,
) -> ClimateEnsemble:
    """
    Load a simple JSON ensemble table.

    Expected format:
    {
      "ssp245": {
        "2050": {"EC-Earth3": 0.08, "MPI-ESM1-2-HR": 0.11, ...}
      }
    }
    Values are relative deltas (fraction).
    """
    path = Path(path)
    data = json.loads(path.read_text())
    members = data.get(ssp, {}).get(str(horizon_year), {})
    if not members:
        raise KeyError(f"No ensemble members for {ssp} / {horizon_year} in {path}")
    return ClimateEnsemble(
        members={k: float(v) for k, v in members.items()},
        ssp=ssp,
        horizon_year=horizon_year,
        source=str(path),
    )
