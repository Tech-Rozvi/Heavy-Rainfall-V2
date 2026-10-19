from .manager import DataAcquisitionManager, AcquisitionResult, resolve_gaul_bounds
try:
    from .zimbabwe_aoi import lookup_zimbabwe_bbox
except ImportError:
    lookup_zimbabwe_bbox = None

__all__ = [
    "DataAcquisitionManager",
    "AcquisitionResult",
    "resolve_gaul_bounds",
    "lookup_zimbabwe_bbox",
]
