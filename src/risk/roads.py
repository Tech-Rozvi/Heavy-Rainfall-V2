"""
Road network intersection with provisional flood depth.

Physical exposure metrics only (length / fraction above depth thresholds).
No disruption cost, no traffic modelling, no financial loss.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Sequence

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

DEFAULT_THRESHOLDS_M = (0.15, 0.50, 1.00)


@dataclass
class RoadExposureReport:
    n_segments: int
    total_length_m: float
    exposed_length_by_threshold_m: dict[str, float]
    exposed_fraction_by_threshold: dict[str, float]
    hazard_validation_status: str = "provisional"
    notes: list[str] = field(default_factory=list)
    method: str = "raster_midpoint_intersection"

    def to_dict(self) -> dict:
        return asdict(self)


def _iter_lines(geom):
    if geom is None or geom.is_empty:
        return
    if geom.geom_type == "LineString":
        yield geom
    elif geom.geom_type == "MultiLineString":
        for g in geom.geoms:
            yield g


def road_hazard_intersection(
    depth_m: np.ndarray,
    roads_gdf: Any,
    transform: Any,
    *,
    thresholds_m: Sequence[float] = DEFAULT_THRESHOLDS_M,
    crs_metric: Optional[str] = None,
    hazard_validation_status: str = "provisional",
) -> RoadExposureReport:
    """
    Estimate road length intersecting cells with depth > each threshold.

    Screening metric: each line segment midpoint is sampled on the depth
    raster; the projected segment length is attributed to thresholds exceeded.
    """
    notes = [
        "Physical road-length exposure only; not traffic disruption or economic loss.",
        "Screening-level raster midpoint sampling; not a centreline hydraulic model.",
    ]
    if hazard_validation_status == "provisional":
        notes.append("Depth layer is provisional; road exposure inherits that status.")

    empty = RoadExposureReport(
        n_segments=0,
        total_length_m=0.0,
        exposed_length_by_threshold_m={f"gt_{t}m": 0.0 for t in thresholds_m},
        exposed_fraction_by_threshold={f"gt_{t}m": 0.0 for t in thresholds_m},
        hazard_validation_status=hazard_validation_status,
        notes=notes + ["No road segments provided."],
    )
    if roads_gdf is None or len(roads_gdf) == 0:
        return empty

    import geopandas as gpd

    if not isinstance(roads_gdf, gpd.GeoDataFrame):
        raise TypeError("roads_gdf must be a GeoDataFrame")

    gdf = roads_gdf
    metric = gdf
    if gdf.crs is not None and getattr(gdf.crs, "is_geographic", False):
        target = crs_metric or "EPSG:3857"
        try:
            metric = gdf.to_crs(target)
        except Exception as exc:
            notes.append(f"Projection for length failed ({exc}); length units may be degrees.")
            metric = gdf

    depth = np.asarray(depth_m, dtype="float64")
    ny, nx = depth.shape
    exposed = {float(t): 0.0 for t in thresholds_m}
    total_len = 0.0
    n_seg = 0

    for idx in gdf.index:
        s_geom = gdf.loc[idx].geometry
        m_geom = metric.loc[idx].geometry
        for s_line, m_line in zip(_iter_lines(s_geom), _iter_lines(m_geom)):
            s_coords = list(s_line.coords)
            m_coords = list(m_line.coords)
            n = min(len(s_coords), len(m_coords))
            if n < 2:
                continue
            n_seg += 1
            for i in range(n - 1):
                mx0, my0 = m_coords[i][0], m_coords[i][1]
                mx1, my1 = m_coords[i + 1][0], m_coords[i + 1][1]
                seg_len = float(np.hypot(mx1 - mx0, my1 - my0))
                total_len += seg_len
                sx = 0.5 * (s_coords[i][0] + s_coords[i + 1][0])
                sy = 0.5 * (s_coords[i][1] + s_coords[i + 1][1])
                try:
                    col, row = ~transform * (sx, sy)
                    r, c = int(round(row)), int(round(col))
                except Exception:
                    continue
                if r < 0 or c < 0 or r >= ny or c >= nx:
                    continue
                d = depth[r, c]
                if not np.isfinite(d):
                    continue
                for t in thresholds_m:
                    if d > t:
                        exposed[float(t)] += seg_len

    by_thr = {f"gt_{t}m": min(float(exposed[float(t)]), total_len) for t in thresholds_m}
    frac = {
        f"gt_{t}m": min(by_thr[f"gt_{t}m"] / total_len, 1.0) if total_len > 0 else 0.0
        for t in thresholds_m
    }
    logger.info("Road exposure: %d parts, total_length=%.1f", n_seg, total_len)
    return RoadExposureReport(
        n_segments=n_seg,
        total_length_m=float(total_len),
        exposed_length_by_threshold_m=by_thr,
        exposed_fraction_by_threshold=frac,
        hazard_validation_status=hazard_validation_status,
        notes=notes,
    )
