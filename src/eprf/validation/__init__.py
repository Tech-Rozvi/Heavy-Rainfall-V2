from .metrics import evaluate_precipitation, evaluate_extremes, spatial_block_cv_indices
from .crossval import blocked_temporal_splits, spatial_holdout_mask
from .gauge_harness import (
    load_station_csv,
    validate_field_against_stations,
    validate_series_pair,
    GaugeValidationReport,
)

__all__ = [
    "evaluate_precipitation",
    "evaluate_extremes",
    "spatial_block_cv_indices",
    "blocked_temporal_splits",
    "spatial_holdout_mask",
    "load_station_csv",
    "validate_field_against_stations",
    "validate_series_pair",
    "GaugeValidationReport",
]
