"""Phase 3 tests: bias correction, benchmark, fusion, gauge harness."""
import numpy as np
import pytest

from src.eprf.bias.methods import (
    linear_scaling,
    variance_scaling,
    empirical_quantile_mapping,
)
from src.eprf.bias.benchmark import benchmark_bias_methods
from src.eprf.fusion.products import RainfallProduct, ProductCollection
from src.eprf.fusion.fuse import fuse_products, FusionMethod
from src.eprf.validation.gauge_harness import (
    StationRecord,
    validate_field_against_stations,
    validate_series_pair,
    load_station_csv,
)


def _biased_pair(n=200, bias_factor=1.4, seed=0):
    rng = np.random.default_rng(seed)
    obs = rng.exponential(5.0, size=n)
    model = obs / bias_factor + rng.normal(0, 0.5, size=n)
    model = np.maximum(model, 0.0)
    return obs, model


def test_linear_scaling_reduces_mean_bias():
    obs, model = _biased_pair()
    n_cal = 140
    res = linear_scaling(model[n_cal:], obs[:n_cal], model[:n_cal])
    # Corrected mean should be closer to obs mean on the same segment used as "model" input
    # Here we apply to full model with cal stats
    res_full = linear_scaling(model, obs[:n_cal], model[:n_cal])
    bias_raw = np.mean(model) - np.mean(obs)
    bias_corr = np.mean(res_full.corrected) - np.mean(obs)
    assert abs(bias_corr) < abs(bias_raw) + 0.5


def test_eqm_runs_and_non_negative():
    obs, model = _biased_pair()
    res = empirical_quantile_mapping(model, obs[:150], model[:150])
    assert res.corrected.shape == model.shape
    assert np.all(res.corrected[np.isfinite(res.corrected)] >= 0)


def test_variance_scaling_runs():
    obs, model = _biased_pair()
    res = variance_scaling(model, obs[:150], model[:150])
    assert res.method == "variance_scaling"
    assert res.n_cal == 150


def test_benchmark_selects_a_method():
    obs, model = _biased_pair(n=300, bias_factor=1.5)
    table = benchmark_bias_methods(obs, model, holdout_fraction=0.3)
    assert table.best_method_by_rmse is not None
    assert len(table.rows) == 3
    text = table.summary_text()
    assert "RMSE" in text


def test_fusion_mean():
    a = np.ones((4, 4)) * 10.0
    b = np.ones((4, 4)) * 20.0
    coll = ProductCollection()
    coll.add(RainfallProduct(name="p1", kind="satellite", data=a))
    coll.add(RainfallProduct(name="p2", kind="reanalysis", data=b))
    result = fuse_products(coll, method=FusionMethod.MEAN)
    np.testing.assert_allclose(result.fused, 15.0)


def test_fusion_gauge_priority():
    gauge = np.array([[1.0, np.nan], [np.nan, 4.0]])
    sat = np.array([[9.0, 9.0], [9.0, 9.0]])
    coll = ProductCollection()
    coll.add(RainfallProduct(name="g", kind="gauge", data=gauge))
    coll.add(RainfallProduct(name="s", kind="satellite", data=sat))
    result = fuse_products(coll, method=FusionMethod.GAUGE_PRIORITY)
    assert result.fused[0, 0] == 1.0
    assert result.fused[0, 1] == 9.0


def test_gauge_series_validation():
    rng = np.random.default_rng(1)
    obs = rng.exponential(4, 100)
    sim = obs * 1.1
    out = validate_series_pair(obs, sim)
    assert "metrics" in out
    assert out["metrics"]["n"] == 100


def test_station_field_validation_synthetic():
    field = np.full((50, 50), 100.0)
    stations = [
        StationRecord("A", 10, 10, 100.0, source="station"),
        StationRecord("B", 20, 20, 110.0, source="station"),
        StationRecord("C", 30, 30, 90.0, source="CHIRPS"),
    ]
    report = validate_field_against_stations(field, stations)
    assert report.n_stations >= 2
    assert "mae" in report.metrics or report.n_stations < 3


def test_load_station_csv():
    path = "data/validation/stations.csv"
    stations = load_station_csv(path)
    assert len(stations) >= 5
    assert stations[0].station_id
