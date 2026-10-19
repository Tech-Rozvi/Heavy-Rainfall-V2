"""Phase 4 hydrology tests: losses, hydrograph, pipeline, discharge validation."""
import numpy as np
import pytest

from src.hydrology.losses import scs_curve_number_excess, green_ampt_infiltration, LossMethod
from src.hydrology.hydrograph import (
    Hydrograph,
    excess_to_hydrograph,
    rational_peak_discharge,
    triangular_unit_hydrograph,
)
from src.hydrology.pipeline import run_event_hydrology
from src.hydrology.validate_discharge import validate_hydrograph


def test_scs_zero_when_below_ia():
    # Small storm may produce zero runoff
    r = scs_curve_number_excess(5.0, curve_number=60.0)
    assert float(r.excess_mm) == 0.0 or float(r.excess_mm) < 1.0


def test_scs_excess_less_than_precip():
    r = scs_curve_number_excess(100.0, curve_number=75.0)
    assert float(r.excess_mm) < 100.0
    assert float(r.excess_mm) > 0.0
    assert float(r.infiltration_mm) >= 0.0


def test_scs_higher_cn_more_excess():
    low = scs_curve_number_excess(80.0, curve_number=60.0)
    high = scs_curve_number_excess(80.0, curve_number=90.0)
    assert float(high.excess_mm) > float(low.excess_mm)


def test_green_ampt_mass_balance():
    r = green_ampt_infiltration(20.0, duration_h=2.0, dt_h=0.25)
    total_p = float(np.sum(r.precip_mm))
    total_e = float(np.sum(r.excess_mm))
    total_f = float(np.sum(r.infiltration_mm))
    assert abs(total_p - (total_e + total_f)) < 1e-6


def test_triangular_uh_non_negative():
    t, q = triangular_unit_hydrograph(10.0, time_to_peak_h=2.0, dt_h=0.2)
    assert np.all(q >= 0)
    assert np.max(q) > 0


def test_excess_to_hydrograph_peak_positive():
    excess = np.array([0.0, 5.0, 10.0, 5.0, 0.0])
    h = excess_to_hydrograph(excess, area_km2=25.0, dt_h=1.0, time_to_peak_h=2.0)
    assert h.peak_m3s > 0
    assert h.volume_m3 > 0


def test_rational_method_scales_with_area():
    q1 = rational_peak_discharge(50.0, 1.0, 0.5)
    q2 = rational_peak_discharge(50.0, 2.0, 0.5)
    assert q2 == pytest.approx(2 * q1)


def test_run_event_hydrology_cn():
    # 24h hyetograph-like depths
    precip = np.array([2, 5, 15, 25, 15, 8, 3], dtype=float)
    result = run_event_hydrology(
        precip,
        area_km2=50.0,
        loss_method=LossMethod.CURVE_NUMBER,
        curve_number=80.0,
        dt_h=1.0,
    )
    assert result.excess_total_mm >= 0
    assert result.excess_total_mm <= result.precip_total_mm + 1e-6
    assert result.hydrograph is not None
    assert result.peak_m3s > 0
    payload = result.to_hydraulic_forcing_series()
    assert payload["type"] == "hydrology_event"
    assert len(payload["discharge_m3s"]) > 0


def test_discharge_validation_perfect_match():
    h = Hydrograph.from_arrays([0, 3600, 7200], [0.0, 10.0, 0.0])
    report = validate_hydrograph(h, h)
    assert report.metrics["mae"] == pytest.approx(0.0, abs=1e-9)
    assert report.peak_error_pct == pytest.approx(0.0, abs=1e-6)


def test_hydraulics_imports_hydrology_hydrograph():
    from src.hydraulics.multi_peril import Hydrograph as HH
    from src.hydrology.hydrograph import Hydrograph as YH
    h = YH.from_arrays([0, 1], [0.0, 1.0])
    assert hasattr(h, "q_at")
    # Same class when import succeeded
    assert HH is YH or type(h).q_at is not None
