"""Bootstrap utilities re-exported / thin wrappers for return-level CIs."""
from __future__ import annotations

from typing import Sequence

import numpy as np

from src.eprf.extremes.gev import return_levels_with_ci, STANDARD_RETURN_PERIODS


def bootstrap_return_levels(
    annual_max: np.ndarray,
    return_periods: Sequence[int] = STANDARD_RETURN_PERIODS,
    n_bootstrap: int = 200,
    ci: float = 0.90,
    random_seed: int = 42,
) -> dict[str, np.ndarray]:
    """Public API wrapper around GEV return-level bootstrap."""
    return return_levels_with_ci(
        annual_max,
        return_periods=return_periods,
        n_bootstrap=n_bootstrap,
        ci=ci,
        random_seed=random_seed,
    )
