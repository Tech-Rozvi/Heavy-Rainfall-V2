"""
Design storm generator for hydraulic forcing.

Produces structured rainfall forcing (depth, intensity, temporal profile)
that can be passed to the separate hydraulics module via the formal interface.

Does NOT compute flood depth or inundation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Optional, Sequence

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)


class TemporalPattern(str, Enum):
    UNIFORM = "uniform"
    ALTERNATING_BLOCK = "alternating_block"
    CHICAGO = "chicago"
    FRONT_LOADED = "front_loaded"
    BACK_LOADED = "back_loaded"


@dataclass
class DesignStorm:
    """Structured rainfall forcing for a single design event."""
    return_period_years: int
    duration_hours: float
    total_depth_mm: float
    peak_intensity_mm_h: float
    temporal_pattern: str
    hyetograph_mm: list[float]          # rainfall depth per timestep
    timestep_hours: float
    confidence: str
    source_return_level_mm: float
    notes: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_hydraulic_forcing(self) -> dict[str, Any]:
        """Machine-readable payload for the hydraulics module."""
        return {
            "type": "design_storm_forcing",
            "schema_version": "1.0",
            "return_period_years": self.return_period_years,
            "duration_hours": self.duration_hours,
            "total_depth_mm": self.total_depth_mm,
            "peak_intensity_mm_h": self.peak_intensity_mm_h,
            "temporal_pattern": self.temporal_pattern,
            "hyetograph_mm": self.hyetograph_mm,
            "timestep_hours": self.timestep_hours,
            "units": {
                "depth": "mm",
                "intensity": "mm/h",
                "time": "hours",
            },
            "confidence": self.confidence,
            "notes": self.notes,
            "metadata": self.metadata,
        }


def _uniform_hyetograph(total_mm: float, duration_h: float, dt_h: float) -> np.ndarray:
    n = max(1, int(round(duration_h / dt_h)))
    return np.full(n, total_mm / n)


def _alternating_block(total_mm: float, duration_h: float, dt_h: float) -> np.ndarray:
    """Simple alternating-block: peak in the middle, decreasing outward."""
    n = max(1, int(round(duration_h / dt_h)))
    # Triangular-ish weights peaked at centre
    centre = (n - 1) / 2.0
    weights = np.array([1.0 / (1.0 + abs(i - centre)) for i in range(n)])
    weights /= weights.sum()
    return weights * total_mm


def _chicago(total_mm: float, duration_h: float, dt_h: float, r: float = 0.4) -> np.ndarray:
    """
    Simplified Chicago hyetograph.
    r = fraction of duration before the peak (typical 0.3–0.5).
    """
    n = max(1, int(round(duration_h / dt_h)))
    peak_idx = int(r * (n - 1))
    weights = np.zeros(n)
    # Linear rise then fall
    for i in range(n):
        if i <= peak_idx:
            weights[i] = (i + 1) / (peak_idx + 1)
        else:
            weights[i] = (n - i) / (n - peak_idx)
    weights /= weights.sum()
    return weights * total_mm


def _front_loaded(total_mm: float, duration_h: float, dt_h: float) -> np.ndarray:
    n = max(1, int(round(duration_h / dt_h)))
    weights = np.linspace(2.0, 0.5, n)
    weights /= weights.sum()
    return weights * total_mm


def _back_loaded(total_mm: float, duration_h: float, dt_h: float) -> np.ndarray:
    n = max(1, int(round(duration_h / dt_h)))
    weights = np.linspace(0.5, 2.0, n)
    weights /= weights.sum()
    return weights * total_mm


_PATTERNS = {
    TemporalPattern.UNIFORM: _uniform_hyetograph,
    TemporalPattern.ALTERNATING_BLOCK: _alternating_block,
    TemporalPattern.CHICAGO: _chicago,
    TemporalPattern.FRONT_LOADED: _front_loaded,
    TemporalPattern.BACK_LOADED: _back_loaded,
}


def generate_design_storm(
    return_level_mm: float,
    return_period_years: int,
    duration_hours: float = 24.0,
    temporal_pattern: TemporalPattern = TemporalPattern.ALTERNATING_BLOCK,
    timestep_hours: float = 1.0,
    confidence: str = "Moderate",
    notes: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
) -> DesignStorm:
    """
    Build a design storm from a return-level depth.

    Important limitation
    --------------------
    When the underlying observations are daily, sub-daily intensities are
    *estimated* by distributing the daily depth.  This is not a substitute
    for true sub-daily IDF analysis.  The notes field records this.
    """
    notes = list(notes or [])
    if duration_hours < 24:
        notes.append(
            "Duration < 24 h requested. If source data are daily, sub-daily "
            "intensities are distributed estimates, not observed IDF values."
        )

    fn = _PATTERNS[temporal_pattern]
    hyeto = fn(return_level_mm, duration_hours, timestep_hours)
    peak = float(np.max(hyeto) / timestep_hours)  # mm/h

    return DesignStorm(
        return_period_years=return_period_years,
        duration_hours=duration_hours,
        total_depth_mm=float(return_level_mm),
        peak_intensity_mm_h=peak,
        temporal_pattern=temporal_pattern.value,
        hyetograph_mm=[float(x) for x in hyeto],
        timestep_hours=timestep_hours,
        confidence=confidence,
        source_return_level_mm=float(return_level_mm),
        notes=notes,
        metadata=metadata or {},
    )
