"""Unit tests for GEV / return-level module."""
import numpy as np
import pytest

from src.eprf.extremes.gev import (
    annual_maxima_series,
    fit_gev_annual_maxima,
    return_levels_with_ci,
    _fit_gev_1d,
    _return_level,
)


def test_annual_maxima_shape():
    rng = np.random.default_rng(0)
    daily = rng.exponential(5, size=(365 * 15, 4, 4))
    am = annual_maxima_series(daily)
    assert am.shape[0] == 15
    assert am.shape[1:] == (4, 4)
    assert np.all(am >= 0)


def test_gev_fit_recover_known():
    # Generate from known Gumbel (shape=0)
    rng = np.random.default_rng(1)
    true_loc, true_scale = 40.0, 12.0
    sample = rng.gumbel(loc=true_loc, scale=true_scale, size=80)
    fit = _fit_gev_1d(sample)
    assert fit.converged or fit.method.startswith("Gumbel")
    assert abs(fit.loc - true_loc) < 8.0  # loose for finite sample
    assert abs(fit.scale - true_scale) < 5.0


def test_return_level_increases_with_T():
    rng = np.random.default_rng(2)
    sample = rng.gumbel(loc=30, scale=10, size=50)
    fit = _fit_gev_1d(sample)
    rl10 = _return_level(fit.shape, fit.loc, fit.scale, 10)
    rl100 = _return_level(fit.shape, fit.loc, fit.scale, 100)
    assert rl100 > rl10


def test_return_levels_with_ci_keys():
    rng = np.random.default_rng(3)
    am = rng.gumbel(loc=25, scale=8, size=(20, 3, 3))
    out = return_levels_with_ci(am, return_periods=[10, 50], n_bootstrap=30, random_seed=0)
    assert "rl_10" in out
    assert "rl_10_lower" in out
    assert "rl_10_upper" in out
    assert "shape" in out
    # CI should bracket the central estimate on average
    assert np.nanmean(out["rl_10_lower"]) <= np.nanmean(out["rl_10"]) + 1e-6
    assert np.nanmean(out["rl_10_upper"]) >= np.nanmean(out["rl_10"]) - 1e-6
