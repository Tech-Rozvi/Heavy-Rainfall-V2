"""
Transparent climate delta-change and related adjustment methods.

Does NOT claim dynamical downscaling.
Does NOT invent CORDEX/WRF fields.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

import numpy as np

from src.utils import get_logger
from src.eprf.interfaces.contracts import ClimateAdjustment, ModuleOutputMeta

logger = get_logger(__name__)


class DeltaMethod(str, Enum):
    ABSOLUTE = "absolute_delta"
    RELATIVE = "relative_delta"
    QUANTILE_DELTA = "quantile_delta_mapping"


def apply_delta_change(
    historical: np.ndarray,
    *,
    delta: float,
    method: DeltaMethod = DeltaMethod.RELATIVE,
    aoi_id: str = "unknown",
    ssp: Optional[str] = None,
    horizon_year: Optional[int] = None,
    baseline_period: tuple[int, int] = (1981, 2010),
    future_period: tuple[int, int] = (2041, 2070),
    is_extreme: bool = False,
) -> tuple[np.ndarray, ClimateAdjustment]:
    """
    Apply a scalar delta to a historical field.

    Parameters
    ----------
    historical : array of rainfall (mm) or intensities
    delta : absolute (mm) or relative (fraction, e.g. 0.10 = +10 %)
    method : absolute or relative
    is_extreme : if True, records that this delta was applied to extremes

    Returns
    -------
    adjusted array, ClimateAdjustment contract
    """
    h = np.asarray(historical, dtype="float64")
    if method == DeltaMethod.ABSOLUTE:
        adjusted = h + delta
        delta_mean_frac = None
        delta_extreme_frac = delta if is_extreme else None
    elif method == DeltaMethod.RELATIVE:
        adjusted = h * (1.0 + delta)
        delta_mean_frac = delta if not is_extreme else None
        delta_extreme_frac = delta if is_extreme else None
    else:
        raise NotImplementedError(
            "Quantile delta mapping requires full distributional tables; "
            "use relative/absolute for scalar application or supply a CORDEX product."
        )

    meta = ModuleOutputMeta(
        aoi_id=aoi_id,
        module="climate_v2.delta",
        scenario=ssp,
        data_kind="projected",
        notes=[
            f"Method: {method.value}",
            "This is NOT dynamical downscaling.",
            "This is NOT a weather forecast.",
        ],
    )
    adj = ClimateAdjustment(
        meta=meta,
        method=method.value,
        ssp=ssp,
        horizon_year=horizon_year,
        baseline_period=baseline_period,
        future_period=future_period,
        delta_mean_frac=delta_mean_frac,
        delta_extreme_frac=delta_extreme_frac,
        is_dynamical_downscaling=False,
        notes=meta.notes,
    )
    return adjusted, adj
