"""Phase 5: hydraulics smoke tests and provisional depth labelling."""
import numpy as np
import pytest

from src.eprf.interfaces.contracts import (
    ModuleOutputMeta,
    RainfallForcing,
    HydraulicResult,
)
from src.eprf.interfaces.hydraulics_bridge import (
    rainfall_forcing_to_hydraulic_run,
    label_depth_product,
    PROVISIONAL_NOTE,
)
from src.hydraulics.solver2d import ShallowWater2D, SolverConfig


def _toy_dem(n=12):
    """Small bowl-shaped DEM for stable short runs."""
    y, x = np.mgrid[0:n, 0:n]
    dem = 10.0 + 0.05 * ((x - n / 2) ** 2 + (y - n / 2) ** 2)
    return dem.astype("float64")


def _forcing(depth_mm=30.0, n_steps=4, dt_h=0.25):
    hyeto = [depth_mm / n_steps] * n_steps
    meta = ModuleOutputMeta(
        aoi_id="smoke_test",
        module="eprf_design_storm",
        data_kind="estimated",
        return_period_years=20,
        confidence="low",
    )
    return RainfallForcing(
        meta=meta,
        total_depth_mm=depth_mm,
        duration_hours=n_steps * dt_h,
        peak_intensity_mm_h=(depth_mm / n_steps) / dt_h,
        hyetograph_mm=hyeto,
        timestep_hours=dt_h,
        temporal_pattern="uniform",
    )


def test_rainfall_forcing_guard():
    f = _forcing()
    f.assert_not_flood_depth()
    f.meta.data_kind = "hydraulically_simulated"
    with pytest.raises(AssertionError):
        f.assert_not_flood_depth()


def test_dry_run_no_depths():
    dem = _toy_dem()
    f = _forcing()
    result = rainfall_forcing_to_hydraulic_run(
        f, dem, bounds=(0, 0, 1, 1), run_solver=False
    )
    assert result.max_depth_m is None
    assert result.is_provisional()
    assert result.meta.data_kind == "hydraulically_simulated"


def test_direct_solver_smoke_produces_depth():
    dem = _toy_dem(10)
    f = _forcing(depth_mm=50.0, n_steps=3, dt_h=0.2)
    result = rainfall_forcing_to_hydraulic_run(
        f,
        dem,
        bounds=(0.0, 0.0, 300.0, 300.0),
        dx=30.0,
        dy=30.0,
        run_solver=True,
        use_direct_solver=True,
        duration_s=900.0,  # 15 minutes wall-clock of simulated time
        manning_n=0.05,
    )
    assert result.validation_status == "provisional"
    assert any("PROVISIONAL" in n for n in result.validation_notes)
    assert result.max_depth_m is not None
    h = np.asarray(result.max_depth_m)
    assert h.shape == dem.shape
    assert float(np.nanmax(h)) >= 0.0
    # With 50 mm rain, some ponding is expected in the bowl
    assert float(np.nanmax(h)) > 0.0


def test_label_depth_product():
    depth = np.array([[0.0, 0.1], [0.2, 0.0]])
    meta = label_depth_product(depth)
    assert meta["validation_status"] == "provisional"
    assert meta["label"] == "provisional_flood_depth"
    assert "PROVISIONAL" in meta["disclaimer"]
    assert meta["max_m"] == pytest.approx(0.2)


def test_solver_runs_without_forcing():
    dem = _toy_dem(8)
    solver = ShallowWater2D(dem, SolverConfig(dx=30, dy=30, max_steps=500))
    state = solver.run(duration_s=60.0, forcing=None)
    assert state.step >= 1
    assert state.h.shape == dem.shape


def test_hydraulic_result_default_provisional():
    meta = ModuleOutputMeta(aoi_id="x", module="hydraulics", data_kind="hydraulically_simulated")
    r = HydraulicResult(meta=meta)
    assert r.is_provisional()
    assert r.product_labels.get("max_depth_m") == "provisional_flood_depth"
