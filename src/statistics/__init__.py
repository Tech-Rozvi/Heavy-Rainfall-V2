"""
Extreme-value statistics for return-period rainfall and depth mapping.

Canonical rainfall EVT API: ``src.eprf.extremes`` and
``src.eprf.extremes.return_period_report``.
This package re-exports legacy hydraulics-oriented helpers and points
new code to EPRF.
"""
from .evt_return_periods import (
    fit_gev,
    fit_gumbel,
    return_level,
    precip_return_period_maps,
    depth_return_period_from_scenario_depths,
    STANDARD_RETURN_PERIODS,
)

# Preferred rainfall EVT surface (EPRF)
try:
    from src.eprf.extremes.gev import (
        fit_gev_annual_maxima,
        return_levels_with_ci,
        annual_maxima_series,
    )
    from src.eprf.extremes.return_period_report import (
        report_return_periods_1d,
        format_return_period_table,
    )
except ImportError:  # pragma: no cover
    fit_gev_annual_maxima = None  # type: ignore
    return_levels_with_ci = None  # type: ignore
    annual_maxima_series = None  # type: ignore
    report_return_periods_1d = None  # type: ignore
    format_return_period_table = None  # type: ignore

__all__ = [
    "fit_gev",
    "fit_gumbel",
    "return_level",
    "precip_return_period_maps",
    "depth_return_period_from_scenario_depths",
    "STANDARD_RETURN_PERIODS",
    "fit_gev_annual_maxima",
    "return_levels_with_ci",
    "annual_maxima_series",
    "report_return_periods_1d",
    "format_return_period_table",
]
