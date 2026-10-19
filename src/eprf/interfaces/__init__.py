"""Formal machine-readable interfaces between modules."""
from .hydraulics_bridge import rainfall_forcing_to_hydraulic_run, label_depth_product
from .contracts import (
    RainfallForcing,
    ClimateAdjustment,
    HydraulicResult,
    ModuleOutputMeta,
)

__all__ = [
    "RainfallForcing",
    "ClimateAdjustment",
    "HydraulicResult",
    "ModuleOutputMeta",
    "rainfall_forcing_to_hydraulic_run",
    "label_depth_product",
]
