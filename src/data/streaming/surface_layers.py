"""
surface_layers.py — Land cover, soil HSG, Manning n, SCS CN, forecast QPF.

Vectorized mappings for 2D SWE friction and infiltration.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

# ESA WorldCover class → Manning n
WORLDCOVER_MANNING: dict[int, float] = {
    10: 0.10,   # Tree cover
    20: 0.06,   # Shrubland
    30: 0.05,   # Grassland
    40: 0.035,  # Cropland
    50: 0.015,  # Built-up
    60: 0.025,  # Bare / sparse
    70: 0.012,  # Snow/ice
    80: 0.030,  # Permanent water (channel-like)
    90: 0.045,  # Herbaceous wetland
    95: 0.08,   # Mangroves
    100: 0.04,  # Moss/lichen
}

# Lookup CN by (WorldCover class, HSG A/B/C/D as 1-4) — TR-55 style simplified
# Columns A B C D
_CN_TABLE: dict[int, tuple[float, float, float, float]] = {
    10: (30, 55, 70, 77),   # forest
    20: (35, 56, 70, 77),   # shrub
    30: (49, 69, 79, 84),   # grass
    40: (67, 78, 85, 89),   # cropland (straight row approx)
    50: (89, 92, 94, 95),   # urban/impervious
    60: (77, 86, 91, 94),   # bare
    70: (98, 98, 98, 98),   # snow/ice
    80: (98, 98, 98, 98),   # water
    90: (85, 85, 85, 85),   # wetland
    95: (85, 85, 85, 85),
    100: (60, 70, 80, 85),
}


def land_cover_to_manning(land_cover: np.ndarray, default_n: float = 0.04) -> np.ndarray:
    """Vectorized WorldCover codes → Manning n grid."""
    lc = np.asarray(land_cover, dtype="float64")
    out = np.full(lc.shape, default_n, dtype="float64")
    for code, n in WORLDCOVER_MANNING.items():
        out = np.where(np.floor(lc) == code, n, out)
    out = np.where(np.isfinite(lc), out, default_n)
    return np.clip(out, 0.01, 0.20)


def sand_clay_to_hsg(sand: np.ndarray, clay: np.ndarray) -> np.ndarray:
    sand = np.asarray(sand, dtype="float64")
    clay = np.asarray(clay, dtype="float64")
    hsg = np.full(np.broadcast(sand, clay).shape, 3.0)
    sand, clay = np.broadcast_arrays(sand, clay)
    hsg = np.full(sand.shape, 3.0)
    hsg = np.where((sand >= 70) & (clay <= 15), 1.0, hsg)
    hsg = np.where((sand >= 50) & (sand < 70) & (clay <= 20), 2.0, hsg)
    hsg = np.where(clay >= 40, 4.0, hsg)
    return hsg


def land_cover_hsg_to_cn(
    land_cover: np.ndarray,
    hsg: np.ndarray,
    default_cn: float = 75.0,
) -> np.ndarray:
    """Combine LC + HSG → SCS Curve Number grid."""
    lc = np.floor(np.asarray(land_cover, dtype="float64"))
    h = np.clip(np.asarray(hsg, dtype="float64"), 1, 4).astype(int)
    out = np.full(lc.shape, default_cn, dtype="float64")
    for code, cn_abcd in _CN_TABLE.items():
        mask = lc == code
        if not np.any(mask):
            continue
        # pick CN by HSG index 0..3
        for hsg_code in (1, 2, 3, 4):
            m = mask & (h == hsg_code)
            out = np.where(m, cn_abcd[hsg_code - 1], out)
    out = np.where(np.isfinite(out), out, default_cn)
    return np.clip(out, 30.0, 98.0)


def fetch_land_cover(
    bounds: tuple[float, float, float, float],
    resolution_m: float = 100.0,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    """ESA WorldCover via Planetary Computer STAC, with cropland fill fallback."""
    minx, miny, maxx, maxy = bounds
    try:
        import planetary_computer
        import pystac_client
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.transform import from_bounds as affine_from_bounds
        from rasterio.enums import Resampling
        import math

        catalog = pystac_client.Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace,
        )
        search = catalog.search(
            collections=["esa-worldcover"],
            bbox=[minx, miny, maxx, maxy],
            max_items=1,
        )
        items = list(search.items())
        if not items:
            raise RuntimeError("No WorldCover items")
        href = planetary_computer.sign(items[0].assets["map"].href)
        mid_lat = (miny + maxy) / 2.0
        m_lat = 111_320.0
        m_lon = 111_320.0 * max(0.2, abs(math.cos(math.radians(mid_lat))))
        h = max(8, int(round((maxy - miny) * m_lat / resolution_m)))
        w = max(8, int(round((maxx - minx) * m_lon / resolution_m)))
        transform = affine_from_bounds(minx, miny, maxx, maxy, w, h)
        with rasterio.open(href) as src:
            window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
            data = src.read(
                1, window=window, out_shape=(h, w),
                resampling=Resampling.nearest, boundless=True, fill_value=0,
            ).astype("float64")
        data = np.where(data <= 0, np.nan, data)
        return {
            "land_cover": data,
            "transform": transform,
            "crs": "EPSG:4326",
            "source": {"provider": "ESA_WorldCover", "access": "PlanetaryComputer"},
        }
    except Exception as exc:
        logger.warning("WorldCover stream failed (%s); uniform cropland class 40", exc)
        return _uniform_lc(bounds, resolution_m, code=40.0, note=str(exc))


def _uniform_lc(bounds, resolution_m, code: float, note: str) -> dict[str, Any]:
    from rasterio.transform import from_bounds as affine_from_bounds
    import math
    minx, miny, maxx, maxy = bounds
    mid_lat = (miny + maxy) / 2.0
    m_lat = 111_320.0
    m_lon = 111_320.0 * max(0.2, abs(math.cos(math.radians(mid_lat))))
    h = max(8, int(round((maxy - miny) * m_lat / resolution_m)))
    w = max(8, int(round((maxx - minx) * m_lon / resolution_m)))
    transform = affine_from_bounds(minx, miny, maxx, maxy, w, h)
    return {
        "land_cover": np.full((h, w), code, dtype="float64"),
        "transform": transform,
        "crs": "EPSG:4326",
        "source": {"provider": "degraded_fill", "note": note},
    }


def fetch_soil_hsg(
    bounds: tuple[float, float, float, float],
    resolution_m: float = 250.0,
) -> dict[str, Any]:
    """SoilGrids REST coarse sample → HSG; fallback HSG C."""
    import math
    from rasterio.transform import from_bounds as affine_from_bounds

    minx, miny, maxx, maxy = bounds
    try:
        import requests
        ny, nx = 10, 10
        lats = np.linspace(maxy, miny, ny)
        lons = np.linspace(minx, maxx, nx)
        sand = np.full((ny, nx), np.nan)
        clay = np.full((ny, nx), np.nan)
        url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                try:
                    r = requests.get(
                        url,
                        params={"lon": float(lon), "lat": float(lat), "depth": "0-5cm", "value": "mean"},
                        timeout=15,
                    )
                    if r.status_code != 200:
                        continue
                    for layer in (r.json().get("properties") or {}).get("layers") or []:
                        name = layer.get("name", "")
                        depths = layer.get("depths") or []
                        if not depths:
                            continue
                        val = depths[0].get("values", {}).get("mean")
                        if val is None:
                            continue
                        v = float(val) / 10.0 if float(val) > 100 else float(val)
                        if "sand" in name:
                            sand[i, j] = v
                        if "clay" in name:
                            clay[i, j] = v
                except Exception:
                    continue
        if not np.isfinite(sand).any():
            raise RuntimeError("empty SoilGrids")
        sand = np.where(np.isfinite(sand), sand, float(np.nanmean(sand)))
        clay = np.where(np.isfinite(clay), clay, float(np.nanmean(clay)))
        hsg = sand_clay_to_hsg(sand, clay)
        transform = affine_from_bounds(minx, miny, maxx, maxy, nx, ny)
        return {
            "sand": sand, "clay": clay, "hsg": hsg,
            "transform": transform, "crs": "EPSG:4326",
            "source": {"provider": "SoilGrids", "access": "ISRIC_REST"},
        }
    except Exception as exc:
        logger.warning("SoilGrids failed (%s); HSG=C", exc)
        mid_lat = (miny + maxy) / 2.0
        m_lat = 111_320.0
        m_lon = 111_320.0 * max(0.2, abs(math.cos(math.radians(mid_lat))))
        h = max(8, int(round((maxy - miny) * m_lat / resolution_m)))
        w = max(8, int(round((maxx - minx) * m_lon / resolution_m)))
        transform = affine_from_bounds(minx, miny, maxx, maxy, w, h)
        return {
            "sand": np.full((h, w), 40.0),
            "clay": np.full((h, w), 30.0),
            "hsg": np.full((h, w), 3.0),
            "transform": transform,
            "crs": "EPSG:4326",
            "source": {"provider": "degraded_HSG_C", "note": str(exc)},
        }


def fetch_forecast_qpf(
    bounds: tuple[float, float, float, float],
    forecast_days: int = 5,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    """Open-Meteo hourly precipitation forecast (1–7 days)."""
    import requests

    forecast_days = int(np.clip(forecast_days, 1, 7))
    minx, miny, maxx, maxy = bounds
    lat, lon = (miny + maxy) / 2.0, (minx + maxx) / 2.0
    url = "https://api.open-meteo.com/v1/forecast"
    r = requests.get(
        url,
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": "precipitation",
            "forecast_days": forecast_days,
            "timezone": "UTC",
        },
        timeout=timeout_s,
    )
    r.raise_for_status()
    hourly = r.json().get("hourly") or {}
    precip = np.asarray(hourly.get("precipitation") or [], dtype="float64")
    times = list(hourly.get("time") or [])
    if precip.size == 0:
        raise RuntimeError("Open-Meteo forecast empty")
    precip = np.maximum(np.nan_to_num(precip, nan=0.0), 0.0)
    total = float(np.nansum(precip))
    peak = float(np.nanmax(precip)) if precip.size else 0.0
    logger.info(
        "Open-Meteo QPF: %d hourly steps, total=%.2f mm, peak=%.2f mm/h at (%.4f, %.4f)",
        precip.size, total, peak, lat, lon,
    )
    if total <= 0.0:
        logger.warning(
            "Open-Meteo QPF is dry (0 mm) for this point/horizon — depth will be ~0. "
            "This can be a true dry forecast, not necessarily a fetch bug."
        )
    return {
        "precipitation_mm_h": precip,
        "times": times,
        "forecast_days": forecast_days,
        "source": {
            "provider": "OpenMeteo_Forecast",
            "url": url,
            "point": {"lat": lat, "lon": lon},
            "total_mm": total,
            "peak_mm_h": peak,
        },
    }


def fetch_osm_buildings(
    bounds: tuple[float, float, float, float],
) -> Any:
    """Download OSM building footprints for AOI via Overpass (geopandas GeoDataFrame)."""
    import geopandas as gpd
    import requests
    from shapely.geometry import shape

    minx, miny, maxx, maxy = bounds
    query = f"""
    [out:json][timeout:60];
    (
      way["building"]({miny},{minx},{maxy},{maxx});
      relation["building"]({miny},{minx},{maxy},{maxx});
    );
    out geom;
    """
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    headers = {
        "User-Agent": "ROZVI/0.10 (flood-risk research; contact: local-user)",
        "Accept": "application/json",
    }
    last_err: Exception | None = None
    r = None
    for url in endpoints:
        try:
            r = requests.post(
                url,
                data={"data": query},
                headers=headers,
                timeout=90,
            )
            if r.status_code == 406:
                last_err = RuntimeError(f"Overpass 406 at {url}")
                logger.warning("Overpass 406 at %s; trying next mirror", url)
                continue
            r.raise_for_status()
            break
        except Exception as exc:
            last_err = exc
            logger.warning("Overpass failed at %s: %s", url, exc)
            r = None
    if r is None:
        raise RuntimeError(f"All Overpass endpoints failed: {last_err}")
    elements = r.json().get("elements") or []
    feats = []
    for el in elements:
        geom = el.get("geometry")
        if not geom:
            continue
        coords = [(p["lon"], p["lat"]) for p in geom]
        if len(coords) < 3:
            continue
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        feats.append({
            "type": "Feature",
            "properties": {
                "id": el.get("id"),
                "building": (el.get("tags") or {}).get("building", "yes"),
            },
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })
    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
    logger.info("OSM buildings: %d features", len(gdf))
    return gdf


def exposure_summary(
    depth_m: np.ndarray,
    transform: Any,
    buildings_gdf: Any,
    thresholds: tuple[float, ...] = (0.15, 0.5, 1.0),
) -> dict[str, Any]:
    """Count buildings intersecting cells with depth > thresholds."""
    import geopandas as gpd
    from rasterio import features
    from shapely.geometry import box

    if buildings_gdf is None or len(buildings_gdf) == 0:
        return {"n_buildings": 0, "by_threshold": {}, "note": "no buildings"}

    depth = np.asarray(depth_m, dtype="float64")
    h, w = depth.shape
    summary: dict[str, Any] = {"n_buildings": int(len(buildings_gdf)), "by_threshold": {}}

    # Max depth under each building via rasterization of max depth zones
    for thr in thresholds:
        mask = (np.nan_to_num(depth, nan=0.0) > thr).astype("uint8")
        # shapes of inundated areas
        shapes = list(features.shapes(mask, mask=mask.astype(bool), transform=transform))
        if not shapes:
            summary["by_threshold"][f"gt_{thr}m"] = 0
            continue
        polys = gpd.GeoDataFrame(
            geometry=[shape(geom) for geom, val in shapes if val == 1],
            crs="EPSG:4326",
        )
        try:
            joined = gpd.sjoin(buildings_gdf, polys, predicate="intersects", how="inner")
            n = int(joined.index.nunique()) if len(joined) else 0
        except Exception:
            n = 0
        summary["by_threshold"][f"gt_{thr}m"] = n
    return summary
