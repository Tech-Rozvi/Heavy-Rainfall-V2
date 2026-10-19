"""Tests for design storms and inter-module contracts."""
import numpy as np
import pytest

from src.eprf.design_storm.generator import (
    generate_design_storm,
    TemporalPattern,
)
from src.eprf.interfaces.contracts import (
    ModuleOutputMeta,
    RainfallForcing,
    ClimateAdjustment,
)
from src.eprf.climate_v2.delta import apply_delta_change, DeltaMethod
from src.eprf.climate_v2.cordex_interface import CORDEXProduct, register_cordex_product, list_cordex_products
from src.eprf.idf.curves import compute_idf_from_daily, SUPPORTED_DURATIONS_DAILY


def test_design_storm_hyetograph_sums_to_total():
    storm = generate_design_storm(
        return_level_mm=120.0,
        return_period_years=50,
        duration_hours=24,
        temporal_pattern=TemporalPattern.ALTERNATING_BLOCK,
        timestep_hours=1.0,
    )
    assert abs(sum(storm.hyetograph_mm) - 120.0) < 1e-6
    assert storm.peak_intensity_mm_h > 0
    forcing = storm.to_hydraulic_forcing()
    assert forcing["type"] == "design_storm_forcing"
    assert forcing["total_depth_mm"] == 120.0


def test_rainfall_forcing_contract():
    meta = ModuleOutputMeta(aoi_id="test", module="test", data_kind="estimated", return_period_years=100)
    rf = RainfallForcing(
        meta=meta,
        total_depth_mm=180.0,
        duration_hours=24,
        peak_intensity_mm_h=25.0,
        hyetograph_mm=[7.5] * 24,
        timestep_hours=1.0,
        temporal_pattern="uniform",
    )
    rf.assert_not_flood_depth()
    d = rf.to_dict()
    assert d["meta"]["data_kind"] == "estimated"


def test_delta_change_relative():
    hist = np.array([100.0, 120.0, 80.0])
    adj, contract = apply_delta_change(
        hist, delta=0.10, method=DeltaMethod.RELATIVE,
        aoi_id="x", ssp="ssp245", horizon_year=2050,
    )
    np.testing.assert_allclose(adj, hist * 1.10)
    assert contract.is_dynamical_downscaling is False
    assert contract.method == "relative_delta"
    assert "NOT dynamical downscaling" in " ".join(contract.notes)


def test_cordex_registration():
    p = CORDEXProduct(
        product_id="cordex_demo",
        driving_gcm="MPI-ESM1-2-HR",
        rcm="REMO2015",
        experiment="ssp245",
        scenario="ssp245",
        historical_period=(1981, 2010),
        future_period=(2041, 2070),
        resolution_km=25.0,
    )
    pid = register_cordex_product(p)
    assert pid == "cordex_demo"
    assert any(x["product_id"] == "cordex_demo" for x in list_cordex_products())


def test_idf_daily_only_by_default():
    rng = np.random.default_rng(0)
    daily = rng.exponential(4, size=365 * 20)
    curves = compute_idf_from_daily(daily, return_periods=[10, 50], durations_hours=[24, 48])
    assert len(curves) == 2
    assert all(c.source == "observed_daily" for c in curves)
    # Sub-daily skipped without flag
    curves2 = compute_idf_from_daily(daily, durations_hours=[1, 24], allow_subdaily_estimate=False)
    assert len(curves2) == 1
    assert curves2[0].duration_hours == 24
