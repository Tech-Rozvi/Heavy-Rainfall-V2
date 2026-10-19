"""
Point and asset hazard queries.

Samples provisional hazard fields (depth, rainfall return level, etc.)
at asset locations.  Always carries the hazard product's validation status.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Sequence

import numpy as np

from src.risk.assets import Asset, AssetCollection
from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class PointHazardResult:
    asset_id: str
    x: float
    y: float
    values: dict[str, float]          # layer_name -> sampled value
    inside_grid: bool
    hazard_validation_status: str = "provisional"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _sample_field(
    field_2d: np.ndarray,
    x: float,
    y: float,
    *,
    transform: Any = None,
    bounds: Optional[tuple[float, float, float, float]] = None,
) -> tuple[Optional[float], bool]:
    """Nearest-neighbour sample; returns (value_or_None, inside)."""
    arr = np.asarray(field_2d, dtype="float64")
    if arr.ndim != 2:
        raise ValueError("field must be 2-D")
    ny, nx = arr.shape

    if transform is not None:
        try:
            col, row = ~transform * (x, y)
            r, c = int(round(row)), int(round(col))
        except Exception:
            return None, False
    elif bounds is not None:
        minx, miny, maxx, maxy = bounds
        if maxx == minx or maxy == miny:
            return None, False
        c = int(round((x - minx) / (maxx - minx) * (nx - 1)))
        r = int(round((maxy - y) / (maxy - miny) * (ny - 1)))
    else:
        # Interpret x,y as column,row indices
        c, r = int(round(x)), int(round(y))

    if r < 0 or c < 0 or r >= ny or c >= nx:
        return None, False
    val = arr[r, c]
    if not np.isfinite(val):
        return None, True
    return float(val), True


def query_point_hazard(
    x: float,
    y: float,
    layers: dict[str, np.ndarray],
    *,
    asset_id: str = "point",
    transform: Any = None,
    bounds: Optional[tuple[float, float, float, float]] = None,
    hazard_validation_status: str = "provisional",
) -> PointHazardResult:
    """
    Sample one or more hazard layers at a single point.

    Parameters
    ----------
    layers : mapping of layer name → 2-D array
        e.g. {"flood_depth_m": hmax, "rain_return_level_mm": rl100}
    """
    values: dict[str, float] = {}
    notes: list[str] = []
    inside_any = False
    for name, field in layers.items():
        val, inside = _sample_field(field, x, y, transform=transform, bounds=bounds)
        inside_any = inside_any or inside
        if val is not None:
            values[name] = val
        elif inside:
            notes.append(f"{name}: nodata at point")
        else:
            notes.append(f"{name}: point outside grid")
    if hazard_validation_status == "provisional":
        notes.append(
            "Hazard layers are provisional; this query is exposure sampling, not risk."
        )
    return PointHazardResult(
        asset_id=asset_id,
        x=x,
        y=y,
        values=values,
        inside_grid=inside_any,
        hazard_validation_status=hazard_validation_status,
        notes=notes,
    )


def query_assets_hazard(
    assets: AssetCollection,
    layers: dict[str, np.ndarray],
    *,
    transform: Any = None,
    bounds: Optional[tuple[float, float, float, float]] = None,
    hazard_validation_status: str = "provisional",
) -> list[PointHazardResult]:
    """Sample hazard layers at every asset location."""
    results = []
    for a in assets.assets:
        results.append(
            query_point_hazard(
                a.x, a.y, layers,
                asset_id=a.asset_id,
                transform=transform,
                bounds=bounds,
                hazard_validation_status=hazard_validation_status,
            )
        )
    logger.info("Queried %d assets against %d layer(s)", len(results), len(layers))
    return results
