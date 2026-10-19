"""Bias correction methods for rainfall products against gauge observations."""
from .methods import (
    linear_scaling,
    variance_scaling,
    empirical_quantile_mapping,
    quantile_mapping,
    BiasCorrectionResult,
)
from .benchmark import benchmark_bias_methods, BiasBenchmarkTable

__all__ = [
    "linear_scaling",
    "variance_scaling",
    "empirical_quantile_mapping",
    "quantile_mapping",
    "BiasCorrectionResult",
    "benchmark_bias_methods",
    "BiasBenchmarkTable",
]
