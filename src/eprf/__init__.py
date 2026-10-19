"""
Extreme Precipitation Risk Framework (EPRF) v8.2.0
(ROZVI rainfall / extremes engine)

Scientifically defensible, reproducible, spatially explicit heavy-rainfall
and extreme-precipitation modelling system.

Primary claims the framework is allowed to make:
- Universal AOI / point / bbox ingestion with explicit CRS confidence.
- Quantitative extreme-value return levels (mm) with bootstrap uncertainty
  and mandatory extrapolation flags when T exceeds record length.
- Transparent climate delta-change and CORDEX/WRF product registration.
- Design-storm rainfall forcing for a separate hydraulics module.
- Spatial and temporal cross-validated performance metrics.

The framework does NOT claim:
- Short-range numerical weather prediction skill.
- Dynamical downscaling of GCMs (it can *register* external CORDEX/WRF products).
- Flood depth or inundation (that remains the separate hydraulics module).
- High confidence for return periods much longer than the observational record.
"""

__version__ = "8.2.0"
__model_name__ = "EPRF"

from .extremes.gev import fit_gev_annual_maxima, return_levels_with_ci
from .features.indices import compute_etccdi_indices
from .validation.metrics import evaluate_precipitation, evaluate_extremes
from .uncertainty.bootstrap import bootstrap_return_levels
from .aoi.ingest import ingest_aoi, AOIRecord
from .aoi.point import point_to_aoi, PointMode
from .aoi.diagnostics import aoi_diagnostic_report

__all__ = [
    "__version__",
    "__model_name__",
    "fit_gev_annual_maxima",
    "return_levels_with_ci",
    "compute_etccdi_indices",
    "evaluate_precipitation",
    "evaluate_extremes",
    "bootstrap_return_levels",
    "ingest_aoi",
    "AOIRecord",
    "point_to_aoi",
    "PointMode",
    "aoi_diagnostic_report",
]
