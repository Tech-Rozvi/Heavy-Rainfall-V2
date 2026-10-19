"""
AOI diagnostic report generated before any modelling run.

Reports geometry validity, CRS confidence, area, data coverage signals,
and explicit warnings when the AOI may fall outside supported domains.
"""
from __future__ import annotations

from typing import Any, Optional

from .ingest import AOIRecord


def aoi_diagnostic_report(
    aoi: AOIRecord,
    *,
    station_count_nearby: Optional[int] = None,
    precip_products: Optional[list[str]] = None,
    climate_products: Optional[list[str]] = None,
    dem_available: Optional[bool] = None,
    domain_bounds: Optional[tuple[float, float, float, float]] = None,
) -> dict[str, Any]:
    """
    Produce a machine-readable diagnostic dict for the given AOI.

    domain_bounds, if supplied, is (minx, miny, maxx, maxy) of the supported
    modelling domain in the working CRS. Overlap is checked and reported.
    """
    warnings = list(aoi.warnings)
    status = "ok"

    if aoi.crs_confidence in ("unknown", "inferred_low"):
        warnings.append(
            f"CRS confidence is '{aoi.crs_confidence}'. "
            "Verify coordinates before interpreting spatial results."
        )
        status = "warning"

    if aoi.area_km2 is not None and aoi.area_km2 > 1_000_000:
        warnings.append(
            f"AOI area is large ({aoi.area_km2:.0f} km²). "
            "Expect long runtimes and coarser effective resolution."
        )

    coverage = {
        "precip_products": precip_products or ["unknown — supply data catalogue"],
        "climate_products": climate_products or ["unknown — supply data catalogue"],
        "dem_available": dem_available,
        "station_count_nearby": station_count_nearby,
    }

    domain_overlap = None
    if domain_bounds is not None:
        minx, miny, maxx, maxy = aoi.bounds
        dminx, dminy, dmaxx, dmaxy = domain_bounds
        overlaps = not (maxx < dminx or minx > dmaxx or maxy < dminy or miny > dmaxy)
        domain_overlap = overlaps
        if not overlaps:
            warnings.append("AOI does not overlap the configured modelling domain.")
            status = "error"

    report = {
        "aoi_id": aoi.aoi_id,
        "status": status,
        "geometry_type": aoi.geometry_type,
        "crs": aoi.crs,
        "original_crs": aoi.original_crs,
        "crs_confidence": aoi.crs_confidence,
        "bounds": aoi.bounds,
        "area_km2": aoi.area_km2,
        "n_features": aoi.n_features,
        "point_mode": aoi.point_mode,
        "buffer_radius_km": aoi.buffer_radius_km,
        "user_coordinate": aoi.user_coordinate,
        "user_crs": aoi.user_crs,
        "source_format": aoi.source_format,
        "coverage": coverage,
        "domain_overlap": domain_overlap,
        "warnings": warnings,
        "recommendation": _recommendation(status, aoi, station_count_nearby),
    }
    return report


def _recommendation(status: str, aoi: AOIRecord, stations: Optional[int]) -> str:
    if status == "error":
        return "Do not proceed until domain overlap and CRS issues are resolved."
    if aoi.crs_confidence == "unknown":
        return "Supply an explicit CRS before production analysis."
    if stations is not None and stations == 0:
        return (
            "No nearby stations detected. Extreme-value estimates will rely on "
            "gridded products only; confidence will be reduced."
        )
    if aoi.point_mode == "point_only":
        return (
            "Point-only mode selected. Results refer to the single coordinate; "
            "no spatial aggregation is performed."
        )
    return "AOI appears usable. Proceed with analysis; review warnings."
