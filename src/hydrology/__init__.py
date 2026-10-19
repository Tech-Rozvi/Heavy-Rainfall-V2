"""
ROZVI hydrology layer — rainfall losses, excess rainfall, and hydrographs.

This package is intentionally separate from ``src.hydraulics``:

  rainfall hyetograph
      → losses / infiltration
      → excess rainfall
      → runoff hydrograph
      → (optional) hydraulic routing

Hydraulics must consume hydrographs / excess rainfall; it must not be the
only place where Curve Number or Green–Ampt logic lives.
"""

__version__ = "0.2.0"

from .losses import (
    scs_curve_number_excess,
    green_ampt_infiltration,
    LossMethod,
    LossResult,
)
from .hydrograph import (
    Hydrograph,
    triangular_unit_hydrograph,
    excess_to_hydrograph,
    rational_peak_discharge,
)
from .pipeline import (
    run_event_hydrology,
    EventHydrologyResult,
)

__all__ = [
    "__version__",
    "scs_curve_number_excess",
    "green_ampt_infiltration",
    "LossMethod",
    "LossResult",
    "Hydrograph",
    "triangular_unit_hydrograph",
    "excess_to_hydrograph",
    "rational_peak_discharge",
    "run_event_hydrology",
    "EventHydrologyResult",
]
