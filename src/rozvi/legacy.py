"""
Legacy product quarantine (Phase 10).

The original weighted-overlay susceptibility path remains available for
diagnostic ranking only.  It must never be labelled or consumed as:

- flood depth / inundation
- quantitative rainfall intensity (mm)
- return level
- financial risk

Use EPRF (`src.eprf`) for extremes and `src.hydraulics` for depth.
"""
from __future__ import annotations

from typing import Any, Optional

from src.utils import get_logger

logger = get_logger(__name__)

LEGACY_PRODUCT = "relative_rainfall_susceptibility"
LEGACY_STATUS = "legacy_diagnostic"
SUSCEPTIBILITY_DISCLAIMER = (
    "LEGACY DIAGNOSTIC ONLY: relative rainfall susceptibility score in [0, 1]. "
    "Not flood depth, not a return level (mm), not a regulatory hazard map, "
    "and not financial risk. Prefer EPRF return levels and (if required) "
    "provisional hydraulic depth products."
)


def susceptibility_product_metadata(
    *,
    source_path: str = "main.run_pipeline",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Standard metadata attached to every susceptibility raster/JSON export."""
    meta = {
        "product": LEGACY_PRODUCT,
        "product_label": "legacy_relative_susceptibility",
        "validation_status": LEGACY_STATUS,
        "units": "dimensionless_score_0_1",
        "is_flood_depth": False,
        "is_return_level": False,
        "is_financial_risk": False,
        "canonical_replacement": {
            "extremes": "src.eprf.extremes / POST /v1/rozvi/return-periods",
            "hydrology": "src.hydrology",
            "flood_depth": "src.hydraulics via RainfallForcing (provisional)",
            "uncertainty": "src.rozvi.chain",
        },
        "disclaimer": SUSCEPTIBILITY_DISCLAIMER,
        "source_path": source_path,
    }
    if extra:
        meta["extra"] = extra
    return meta


def warn_legacy_susceptibility() -> None:
    """Emit a single clear log warning when the legacy path is used."""
    logger.warning(SUSCEPTIBILITY_DISCLAIMER)


def is_legacy_susceptibility_metadata(meta: dict[str, Any]) -> bool:
    return meta.get("product") == LEGACY_PRODUCT or meta.get("product_label") == (
        "legacy_relative_susceptibility"
    )
