"""
Risk snapshot report — composes hazard, exposure, and asset queries.

Explicitly does **not** produce financial loss or damage ratios.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

from src.risk.assets import AssetCollection
from src.risk.query import PointHazardResult, query_assets_hazard
from src.risk.roads import RoadExposureReport
from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class RiskSnapshot:
    """
    Composed physical-risk intelligence product.

    Layers:
      - hazard: references only (validation status, product labels)
      - assets: query results at asset locations
      - buildings: optional count summary
      - roads: optional length exposure
    """
    aoi_id: str
    timestamp_utc: str
    hazard_products: dict
    asset_results: list[dict] = field(default_factory=list)
    building_exposure: Optional[dict] = None
    road_exposure: Optional[dict] = None
    disclaimers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_risk_snapshot(
    aoi_id: str,
    *,
    hazard_layers: Optional[dict] = None,
    hazard_validation_status: str = "provisional",
    assets: Optional[AssetCollection] = None,
    asset_results: Optional[list[PointHazardResult]] = None,
    building_exposure: Optional[dict] = None,
    road_exposure: Optional[RoadExposureReport] = None,
    transform: Any = None,
    bounds: Optional[tuple] = None,
) -> RiskSnapshot:
    """
    Assemble a risk snapshot from available components.

    Any missing component is left null — never fabricated.
    """
    disclaimers = [
        "Rainfall susceptibility is not flood hazard.",
        "Flood depth products may be provisional and inherit into exposure.",
        "Exposure counts/lengths are physical metrics only — not financial risk.",
        "This snapshot is not an insured-loss or regulatory design product.",
    ]
    notes = []

    hazard_products = {
        "validation_status": hazard_validation_status,
        "layers": list((hazard_layers or {}).keys()),
        "label": (
            "provisional_flood_depth"
            if hazard_validation_status == "provisional"
            else "flood_depth"
        ),
    }

    results_dicts: list[dict] = []
    if asset_results is not None:
        results_dicts = [r.to_dict() for r in asset_results]
    elif assets is not None and hazard_layers:
        queried = query_assets_hazard(
            assets,
            hazard_layers,
            transform=transform,
            bounds=bounds,
            hazard_validation_status=hazard_validation_status,
        )
        results_dicts = [r.to_dict() for r in queried]
    elif assets is not None:
        notes.append("Assets provided but no hazard layers to sample.")

    road_dict = road_exposure.to_dict() if road_exposure is not None else None
    if building_exposure is not None and "note" not in building_exposure:
        building_exposure = {
            **building_exposure,
            "note": "Physical structure counts only; no monetary damage estimates.",
        }

    return RiskSnapshot(
        aoi_id=aoi_id,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        hazard_products=hazard_products,
        asset_results=results_dicts,
        building_exposure=building_exposure,
        road_exposure=road_dict,
        disclaimers=disclaimers,
        notes=notes,
    )
