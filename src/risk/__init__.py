"""
ROZVI risk / asset layer.

Separation of concerns (enforced in APIs and reports):
  rainfall / extremes  ≠  flood depth  ≠  exposure  ≠  risk

This package provides:
- asset and address query schemas
- sampling of provisional hazard fields at points/assets
- road network intersection with depth thresholds
- exposure summaries (physical counts only)

It does **not** compute insured loss, damage ratios, or financial risk.
"""

__version__ = "0.5.0"

from .assets import Asset, AssetCollection, load_assets_csv, load_assets_geojson, assets_from_coordinates
from .query import query_point_hazard, query_assets_hazard, PointHazardResult
from .roads import road_hazard_intersection, RoadExposureReport
from .report import build_risk_snapshot, RiskSnapshot

__all__ = [
    "__version__",
    "Asset",
    "AssetCollection",
    "load_assets_csv",
    "load_assets_geojson",
    "assets_from_coordinates",
    "query_point_hazard",
    "query_assets_hazard",
    "PointHazardResult",
    "road_hazard_intersection",
    "RoadExposureReport",
    "build_risk_snapshot",
    "RiskSnapshot",
]
