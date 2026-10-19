"""Physics-based 2D hydraulic routing, multi-peril forcing, and event validation."""
from .solver2d import ShallowWater2D, SolverConfig, SolverState
from .multi_peril import (
    MultiPerilForcing,
    PerilConfig,
    Hydrograph,
    build_forcing_from_layers,
)
from .validate_depth import (
    HighWaterMark,
    DepthValidationReport,
    compare_high_water_marks,
    compare_inundation_footprint,
    evaluate_event_depth,
    apply_validation_to_labels,
)
from .event_catalogue import (
    FloodEventRecord,
    load_high_water_marks_csv,
    save_validation_report,
)

__all__ = [
    "ShallowWater2D",
    "SolverConfig",
    "SolverState",
    "MultiPerilForcing",
    "PerilConfig",
    "Hydrograph",
    "build_forcing_from_layers",
    "HighWaterMark",
    "DepthValidationReport",
    "compare_high_water_marks",
    "compare_inundation_footprint",
    "evaluate_event_depth",
    "apply_validation_to_labels",
    "FloodEventRecord",
    "load_high_water_marks_csv",
    "save_validation_report",
]
