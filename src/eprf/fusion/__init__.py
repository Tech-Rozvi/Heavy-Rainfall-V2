"""Multi-source rainfall product interface and simple fusion."""
from .products import RainfallProduct, ProductCollection
from .fuse import fuse_products, FusionResult, FusionMethod

__all__ = [
    "RainfallProduct",
    "ProductCollection",
    "fuse_products",
    "FusionResult",
    "FusionMethod",
]
