"""
Interface for externally produced dynamical downscaling products (CORDEX, WRF, …).

This module does NOT run a regional climate model.
It registers and validates metadata of products supplied by the user or
an external pipeline so that the rainfall and risk modules can consume them
with full provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class CORDEXProduct:
    """Metadata record for a dynamically downscaled climate product."""
    product_id: str
    driving_gcm: str
    rcm: str
    experiment: str                       # historical | ssp245 | ...
    scenario: Optional[str]
    historical_period: tuple[int, int]
    future_period: Optional[tuple[int, int]]
    resolution_km: float
    variable: str = "pr"
    path: Optional[str] = None
    bias_correction: Optional[str] = None
    physics_config: Optional[str] = None
    source: str = "external"
    is_dynamical_downscaling: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# In-memory registry for the current process / session
_REGISTRY: dict[str, CORDEXProduct] = {}


def register_cordex_product(product: CORDEXProduct) -> str:
    """Register a CORDEX/WRF product. Returns product_id."""
    if product.path and not Path(product.path).exists():
        product.notes.append(
            f"Path {product.path} does not exist on this system; "
            "register for provenance only."
        )
    _REGISTRY[product.product_id] = product
    return product.product_id


def get_cordex_product(product_id: str) -> Optional[CORDEXProduct]:
    return _REGISTRY.get(product_id)


def list_cordex_products() -> list[dict[str, Any]]:
    return [p.to_dict() for p in _REGISTRY.values()]
