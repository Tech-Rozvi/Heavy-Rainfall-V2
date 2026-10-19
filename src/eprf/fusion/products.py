"""
Rainfall product containers with provenance fields.

A product is one source (gauge, CHIRPS, IMERG, ERA5, …) at a defined
spatial/temporal support.  Fusion operates on aligned ProductCollections.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import numpy as np


@dataclass
class RainfallProduct:
    """Single rainfall data product (array + metadata)."""
    name: str
    kind: str  # gauge | satellite | reanalysis | model | fused | bias_corrected
    data: np.ndarray
    units: str = "mm"
    temporal_resolution: str = "daily"
    spatial_resolution: Optional[str] = None
    crs: Optional[str] = None
    provider: Optional[str] = None
    version: Optional[str] = None
    path: Optional[str] = None
    quality_flags: Optional[np.ndarray] = None
    notes: list[str] = field(default_factory=list)

    def to_meta_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("data", None)
        d.pop("quality_flags", None)
        d["shape"] = list(np.asarray(self.data).shape)
        d["finite_fraction"] = float(np.isfinite(self.data).mean()) if self.data.size else 0.0
        return d


@dataclass
class ProductCollection:
    """Named set of rainfall products for the same analysis domain."""
    products: dict[str, RainfallProduct] = field(default_factory=dict)
    alignment_note: str = ""

    def add(self, product: RainfallProduct) -> None:
        self.products[product.name] = product

    def names(self) -> list[str]:
        return list(self.products.keys())

    def get(self, name: str) -> RainfallProduct:
        return self.products[name]

    def meta_table(self) -> list[dict]:
        return [p.to_meta_dict() for p in self.products.values()]
