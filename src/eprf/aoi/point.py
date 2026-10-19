"""First-class point analysis mode."""
from __future__ import annotations

from enum import Enum
from typing import Optional, Sequence

from .ingest import AOIRecord, ingest_aoi


class PointMode(str, Enum):
    POINT_ONLY = "point_only"
    BUFFER = "buffer"
    NEAREST_CELL = "nearest_cell"
    NEIGHBOURHOOD = "neighbourhood"


def point_to_aoi(
    x: float,
    y: float,
    *,
    crs: Optional[str] = None,
    mode: PointMode = PointMode.BUFFER,
    buffer_km: float = 10.0,
) -> AOIRecord:
    """
    Convert a single coordinate into an AOIRecord.

    The user-supplied coordinate is preserved in ``user_coordinate``.
    The analysis footprint (buffer / neighbourhood) is stored separately
    so that reports can distinguish the requested point from the modelled region.
    """
    return ingest_aoi(
        point=(x, y),
        crs=crs,
        buffer_km=buffer_km if mode in (PointMode.BUFFER, PointMode.NEIGHBOURHOOD) else None,
        point_mode=mode.value,
    )
