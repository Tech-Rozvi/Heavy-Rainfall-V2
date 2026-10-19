"""
exposure.py — OSM buildings / roads overlay on flood depth rasters.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

DEFAULT_THRESHOLDS_M = (0.15, 0.50, 1.00)


def load_osm_buildings(
    bounds: tuple[float, float, float, float],
    *,
    timeout_s: float = 90.0,
) -> Any:
    """Fetch building footprints for AOI via Overpass API → GeoDataFrame."""
    from src.data.streaming.surface_layers import fetch_osm_buildings

    return fetch_osm_buildings(bounds)


def load_osm_roads(
    bounds: tuple[float, float, float, float],
    *,
    timeout_s: float = 90.0,
) -> Any:
    """Fetch highway ways for AOI via Overpass (optional roads layer)."""
    import geopandas as gpd
    import requests

    minx, miny, maxx, maxy = bounds
    query = f"""
    [out:json][timeout:60];
    (
      way["highway"]({miny},{minx},{maxy},{maxx});
    );
    out geom;
    """
    try:
        r = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=timeout_s,
        )
        r.raise_for_status()
        elements = r.json().get("elements") or []
    except Exception as e:
        logger.warning("OSM roads fetch failed: %s", e)
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    feats = []
    for el in elements:
        geom = el.get("geometry")
        if not geom or len(geom) < 2:
            continue
        coords = [(p["lon"], p["lat"]) for p in geom]
        feats.append({
            "type": "Feature",
            "properties": {
                "id": el.get("id"),
                "highway": (el.get("tags") or {}).get("highway", "yes"),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        })
    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
    logger.info("OSM roads: %d features", len(gdf))
    return gdf


def building_exposure_report(
    depth_m: np.ndarray,
    transform: Any,
    bounds: tuple[float, float, float, float],
    *,
    thresholds_m: Sequence[float] = DEFAULT_THRESHOLDS_M,
    buildings_gdf: Any = None,
) -> dict[str, Any]:
    """
    Count structures intersecting cells with depth > each threshold.
    Physical counts only — no financial loss metrics.
    """
    from src.data.streaming.surface_layers import exposure_summary

    if buildings_gdf is None:
        try:
            buildings_gdf = load_osm_buildings(bounds)
        except Exception as e:
            logger.warning("Buildings unavailable: %s", e)
            return {
                "n_buildings": 0,
                "by_threshold": {f"gt_{t}m": 0 for t in thresholds_m},
                "error": str(e),
            }
    summary = exposure_summary(
        depth_m, transform, buildings_gdf, thresholds=tuple(thresholds_m)
    )
    summary["thresholds_m"] = list(thresholds_m)
    summary["note"] = "Physical structure counts only; no monetary damage estimates."
    return summary
