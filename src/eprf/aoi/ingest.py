"""
Universal AOI ingestion and normalization.

Accepts vector, raster, bounding box, or point inputs and produces a
standardized AOIRecord used by all downstream modules.

Scientific principle: never silently assume CRS. Missing CRS is flagged
with confidence = "unknown" and the caller must supply it or accept
explicit inference with documented confidence.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence, Union

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

WORKING_CRS = "EPSG:4326"
SUPPORTED_VECTOR = {".geojson", ".json", ".shp", ".gpkg", ".kml", ".gml", ".csv", ".xlsx", ".xls", ".wkt", ".zip"}
SUPPORTED_RASTER = {".tif", ".tiff", ".nc", ".netcdf", ".grib", ".grb"}


@dataclass
class AOIRecord:
    """Standardized internal representation of an Area of Interest."""
    aoi_id: str
    geometry_type: str                    # Point | Polygon | MultiPolygon | BBox | RasterMask
    crs: str                              # EPSG or WKT of the *working* geometry
    original_crs: Optional[str]
    crs_confidence: str                   # "user_supplied" | "detected" | "inferred_low" | "unknown"
    bounds: tuple[float, float, float, float]  # (minx, miny, maxx, maxy) in working CRS
    area_km2: Optional[float]
    n_features: int
    geojson: dict                         # standardized GeoJSON (WGS84)
    analysis_mask_bounds: tuple[float, float, float, float]
    point_mode: Optional[str] = None      # None | "point_only" | "buffer" | "nearest_cell" | "neighbourhood"
    buffer_radius_km: Optional[float] = None
    user_coordinate: Optional[tuple[float, float]] = None
    user_crs: Optional[str] = None
    source_path: Optional[str] = None
    source_format: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: Optional[Union[str, Path]] = None) -> str:
        text = json.dumps(self.to_dict(), indent=2, default=str)
        if path:
            Path(path).write_text(text)
        return text


def _stable_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return "shapefile_zip"
    if suffix in SUPPORTED_VECTOR:
        return suffix.lstrip(".")
    if suffix in SUPPORTED_RASTER:
        return suffix.lstrip(".")
    # Peek at content for extension-less or misnamed files
    try:
        head = path.read_bytes()[:200].decode("utf-8", errors="ignore").strip()
        if head.startswith("{") or head.startswith("["):
            return "geojson"
        if head.upper().startswith("POLYGON") or head.upper().startswith("POINT"):
            return "wkt"
    except Exception:
        pass
    return "unknown"


def _load_geodataframe(path: Path, fmt: str, crs_override: Optional[str] = None):
    import geopandas as gpd
    import pandas as pd
    from shapely import wkt as shapely_wkt

    if fmt == "shapefile_zip":
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(tmp)
            shp = list(Path(tmp).rglob("*.shp"))
            if not shp:
                raise ValueError("ZIP archive contains no .shp file")
            gdf = gpd.read_file(shp[0])
    elif fmt in ("geojson", "json"):
        gdf = gpd.read_file(path)
    elif fmt == "gpkg":
        gdf = gpd.read_file(path)
    elif fmt in ("kml", "gml"):
        gdf = gpd.read_file(path, driver="KML")
    elif fmt == "csv":
        df = pd.read_csv(path)
        gdf = _coords_dataframe_to_gdf(df, crs_override)
    elif fmt in ("xlsx", "xls"):
        df = pd.read_excel(path)
        gdf = _coords_dataframe_to_gdf(df, crs_override)
    elif fmt == "wkt":
        text = path.read_text().strip()
        geom = shapely_wkt.loads(text)
        gdf = gpd.GeoDataFrame(geometry=[geom], crs=crs_override or None)
    elif fmt == "shp":
        gdf = gpd.read_file(path)
    else:
        # Fallback: let geopandas try
        gdf = gpd.read_file(path)

    if crs_override:
        if gdf.crs is None:
            gdf = gdf.set_crs(crs_override)
        else:
            gdf = gdf.to_crs(crs_override)
    return gdf


def _coords_dataframe_to_gdf(df, crs_override: Optional[str] = None):
    import geopandas as gpd
    from shapely.geometry import Point

    cols = {c.lower(): c for c in df.columns}
    lon_keys = ["lon", "longitude", "long", "x", "easting", "east"]
    lat_keys = ["lat", "latitude", "y", "northing", "north"]
    lon_col = next((cols[k] for k in lon_keys if k in cols), None)
    lat_col = next((cols[k] for k in lat_keys if k in cols), None)
    if lon_col is None or lat_col is None:
        raise ValueError(
            "CSV/Excel must contain coordinate columns "
            "(lon/longitude/x/easting and lat/latitude/y/northing)"
        )
    geometry = [Point(xy) for xy in zip(df[lon_col], df[lat_col])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs=crs_override or None)
    return gdf


def _repair_geometries(gdf):
    from shapely.validation import make_valid
    fixed = []
    for g in gdf.geometry:
        if g is None or g.is_empty:
            continue
        if not g.is_valid:
            g = make_valid(g)
        fixed.append(g)
    gdf = gdf.iloc[:0].copy()
    if fixed:
        import geopandas as gpd
        gdf = gpd.GeoDataFrame(geometry=fixed, crs=gdf.crs)
    return gdf


def _bbox_to_gdf(xmin: float, ymin: float, xmax: float, ymax: float, crs: str):
    import geopandas as gpd
    from shapely.geometry import box
    return gpd.GeoDataFrame(geometry=[box(xmin, ymin, xmax, ymax)], crs=crs)


def ingest_aoi(
    source: Optional[Union[str, Path]] = None,
    *,
    bbox: Optional[Sequence[float]] = None,
    point: Optional[Sequence[float]] = None,
    crs: Optional[str] = None,
    buffer_km: Optional[float] = None,
    point_mode: str = "buffer",
    dissolve: bool = True,
    working_crs: str = WORKING_CRS,
) -> AOIRecord:
    """
    Ingest any supported AOI representation into a standardized AOIRecord.

    Parameters
    ----------
    source : path to vector/raster file, or None when using bbox/point
    bbox : (xmin, ymin, xmax, ymax) in the supplied CRS
    point : (x, y) or (lon, lat) in the supplied CRS
    crs : CRS of the input coordinates/file (required if not embedded)
    buffer_km : buffer radius for point mode
    point_mode : "point_only" | "buffer" | "nearest_cell" | "neighbourhood"
    dissolve : dissolve multi-feature inputs to a single analysis polygon
    working_crs : internal working CRS (default EPSG:4326)
    """
    warnings: list[str] = []
    original_crs = crs
    crs_confidence = "user_supplied" if crs else "unknown"
    source_path = str(source) if source else None
    source_format = None
    user_coordinate = None

    import geopandas as gpd
    from shapely.ops import unary_union

    if source is not None:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"AOI source not found: {path}")
        fmt = _detect_format(path)
        source_format = fmt
        if fmt in ("tif", "tiff", "nc", "netcdf", "grib", "grb"):
            # Raster → use footprint as AOI
            import rasterio
            with rasterio.open(path) as ds:
                b = ds.bounds
                rcrs = str(ds.crs) if ds.crs else None
                if rcrs:
                    original_crs = rcrs
                    crs_confidence = "detected"
                elif crs:
                    original_crs = crs
                    crs_confidence = "user_supplied"
                else:
                    warnings.append(
                        "Raster has no CRS and none was supplied. "
                        "Coordinates are treated as working CRS; verify this is correct."
                    )
                    original_crs = working_crs
                    crs_confidence = "inferred_low"
                gdf = _bbox_to_gdf(b.left, b.bottom, b.right, b.top, original_crs)
        else:
            gdf = _load_geodataframe(path, fmt, crs_override=crs)
            if gdf.crs is not None:
                original_crs = str(gdf.crs)
                crs_confidence = "detected" if crs is None else "user_supplied"
            elif crs:
                gdf = gdf.set_crs(crs)
                original_crs = crs
                crs_confidence = "user_supplied"
            else:
                warnings.append(
                    "Vector has no CRS and none was supplied. "
                    "Refusing to guess. Please re-call with crs= parameter."
                )
                # Still proceed with working CRS but flag heavily
                gdf = gdf.set_crs(working_crs)
                original_crs = working_crs
                crs_confidence = "unknown"
                warnings.append("CRS confidence = unknown; results may be spatially incorrect.")

    elif bbox is not None:
        if len(bbox) != 4:
            raise ValueError("bbox must be (xmin, ymin, xmax, ymax)")
        if crs is None:
            warnings.append("BBox CRS not supplied; assuming working CRS.")
            crs = working_crs
            crs_confidence = "inferred_low"
        else:
            crs_confidence = "user_supplied"
        original_crs = crs
        gdf = _bbox_to_gdf(bbox[0], bbox[1], bbox[2], bbox[3], crs)
        source_format = "bbox"

    elif point is not None:
        if len(point) != 2:
            raise ValueError("point must be (x, y) or (lon, lat)")
        if crs is None:
            # Heuristic: if |coord| <= 180/90 treat as geographic with low confidence
            if abs(point[0]) <= 180 and abs(point[1]) <= 90:
                crs = "EPSG:4326"
                crs_confidence = "inferred_low"
                warnings.append(
                    "Point CRS not supplied; inferred EPSG:4326 because coordinates "
                    "lie within geographic range. Supply crs= explicitly for production use."
                )
            else:
                raise ValueError(
                    "Point CRS is required when coordinates fall outside typical "
                    "geographic range. Example: crs='EPSG:32736'"
                )
        else:
            crs_confidence = "user_supplied"
        original_crs = crs
        user_coordinate = (float(point[0]), float(point[1]))
        from shapely.geometry import Point as ShapelyPoint
        gdf = gpd.GeoDataFrame(
            geometry=[ShapelyPoint(point[0], point[1])],
            crs=crs,
        )
        source_format = "point"
        # Apply buffer if requested
        if point_mode in ("buffer", "neighbourhood") and buffer_km and buffer_km > 0:
            # Buffer in a suitable projected CRS
            gdf_proj = gdf.to_crs("EPSG:3857")
            gdf_proj["geometry"] = gdf_proj.buffer(buffer_km * 1000.0)
            gdf = gdf_proj.to_crs(crs)
        elif point_mode == "point_only":
            pass  # keep as point
        # nearest_cell / neighbourhood handled downstream by the analysis engine

    else:
        raise ValueError("Provide one of: source, bbox, or point")

    # Repair
    gdf = _repair_geometries(gdf)
    if len(gdf) == 0:
        raise ValueError("AOI contains no valid geometries after repair")

    # Dissolve optional
    if dissolve and len(gdf) > 1:
        union = unary_union(gdf.geometry.values)
        gdf = gpd.GeoDataFrame(geometry=[union], crs=gdf.crs)

    # Reproject to working CRS
    if str(gdf.crs) != working_crs:
        gdf = gdf.to_crs(working_crs)

    # Metrics
    bounds = tuple(float(x) for x in gdf.total_bounds)  # type: ignore
    try:
        area_m2 = gdf.to_crs("EPSG:3857").area.sum()
        area_km2 = float(area_m2 / 1e6)
    except Exception:
        area_km2 = None

    geom_types = set(gdf.geometry.geom_type)
    if len(geom_types) == 1:
        geometry_type = geom_types.pop()
    else:
        geometry_type = "Mixed"

    # Standardized GeoJSON
    geojson = json.loads(gdf.to_json())

    # Stable ID
    hash_payload = json.dumps(
        {"bounds": bounds, "crs": working_crs, "n": len(gdf), "type": geometry_type},
        sort_keys=True,
    )
    aoi_id = _stable_hash(hash_payload)

    record = AOIRecord(
        aoi_id=aoi_id,
        geometry_type=geometry_type,
        crs=working_crs,
        original_crs=original_crs,
        crs_confidence=crs_confidence,
        bounds=bounds,  # type: ignore
        area_km2=area_km2,
        n_features=int(len(gdf)),
        geojson=geojson,
        analysis_mask_bounds=bounds,  # type: ignore
        point_mode=point_mode if source_format == "point" else None,
        buffer_radius_km=buffer_km if source_format == "point" else None,
        user_coordinate=user_coordinate,
        user_crs=original_crs if source_format == "point" else None,
        source_path=source_path,
        source_format=source_format,
        metadata={
            "dissolve": dissolve,
            "working_crs": working_crs,
        },
        warnings=warnings,
    )
    logger.info(
        "AOI ingested id=%s type=%s crs=%s confidence=%s area_km2=%s",
        aoi_id, geometry_type, working_crs, crs_confidence, area_km2,
    )
    return record
