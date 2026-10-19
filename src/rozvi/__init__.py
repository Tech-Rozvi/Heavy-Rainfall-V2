"""
ROZVI — Climate, flood and risk intelligence platform (foundation layer).

Version policy
--------------
ROZVI platform version and EPRF scientific-engine version are tracked
separately.  EPRF remains the rainfall / extremes engine inside ROZVI.
"""

__version__ = "0.11.0"
__platform_name__ = "ROZVI"
__eprf_version__ = "8.2.0"

from src.rozvi.chain import (
    ChainUncertainty,
    StageUncertainty,
    build_chain,
    provenance_for_chain,
    weakest_confidence,
)
from src.eprf import (
    ingest_aoi,
    AOIRecord,
    point_to_aoi,
    PointMode,
    aoi_diagnostic_report,
)

__all__ = [
    "__version__",
    "__platform_name__",
    "__eprf_version__",
    "ingest_aoi",
    "AOIRecord",
    "point_to_aoi",
    "PointMode",
    "aoi_diagnostic_report",
    "ChainUncertainty",
    "StageUncertainty",
    "build_chain",
    "provenance_for_chain",
    "weakest_confidence",
]
