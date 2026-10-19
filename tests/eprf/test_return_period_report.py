"""Tests for rich return-period reporting with extrapolation flags."""
import numpy as np
import pytest

from src.eprf.extremes.return_period_report import (
    report_return_periods_1d,
    format_return_period_table,
    _confidence_class,
)


def test_confidence_downgrades_for_long_T():
    conf, reason = _confidence_class(n_years=30, T=500, ci_width_frac=0.2, converged=True)
    assert conf in ("Low", "Very low")
    assert "Extrapolation" in reason or "ratio" in reason.lower()


def test_short_record_very_low():
    conf, _ = _confidence_class(n_years=5, T=10, ci_width_frac=0.1, converged=True)
    assert conf == "Very low"


def test_report_flags_extrapolation():
    rng = np.random.default_rng(0)
    # 25 years of Gumbel-like annual maxima
    am = rng.gumbel(loc=40, scale=10, size=25)
    results = report_return_periods_1d(am, return_periods=[10, 100, 500], n_bootstrap=30)
    assert len(results) == 3
    r10 = results[0]
    r500 = results[2]
    assert r10.return_period_years == 10
    assert r500.exceeds_record is True
    assert r500.extrapolation_ratio == pytest.approx(500 / 25)
    assert r500.confidence in ("Low", "Very low")
    assert r10.estimate_mm < r500.estimate_mm or not np.isfinite(r500.estimate_mm)


def test_format_table_contains_extrapolated_label():
    rng = np.random.default_rng(1)
    am = rng.gumbel(loc=30, scale=8, size=20)
    results = report_return_periods_1d(am, return_periods=[10, 200], n_bootstrap=20)
    table = format_return_period_table(results)
    assert "EXTRAPOLATED" in table
