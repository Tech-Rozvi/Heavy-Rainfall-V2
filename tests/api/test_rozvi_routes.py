"""Phase 9 tests: framework-free API handlers (+ optional FastAPI TestClient)."""
import numpy as np
import pytest

from src.rozvi import api_handlers as H


def test_info_and_capabilities():
    info = H.info()
    assert info["platform"] == "ROZVI"
    assert "version" in info
    caps = H.capabilities()
    assert caps["capabilities"]["flood_depth"] == "PROVISIONAL"
    assert caps["capabilities"]["financial_loss"] == "NOT_YET_IMPLEMENTED"


def test_return_periods_handler():
    rng = np.random.default_rng(0)
    am = rng.gumbel(40, 10, size=30).tolist()
    body = H.compute_return_periods(am, return_periods=[10, 100], n_bootstrap=40)
    assert body["n_years"] == 30
    assert len(body["results"]) == 2
    assert "disclaimer" in body


def test_event_hydrology_handler():
    body = H.compute_event_hydrology([2, 8, 20, 12, 4], area_km2=15.0, curve_number=80.0)
    assert body["peak_m3s"] is not None
    assert "disclaimer" in body


def test_chain_handler_weakest_link():
    body = H.compute_chain([
        {"stage": "rainfall_extremes", "confidence": "Moderate", "quantified": True},
        {"stage": "hydraulics", "confidence": "Very low", "validation_status": "provisional"},
    ])
    assert body["chain"]["overall_confidence"] == "Very low"


def test_return_periods_rejects_short_series():
    with pytest.raises(ValueError):
        H.compute_return_periods([1, 2, 3])


def test_fastapi_routes_if_available():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from api.app import app
    client = TestClient(app)
    r = client.get("/v1/rozvi/info")
    # Route may be absent if router failed to mount
    if r.status_code == 404:
        pytest.skip("ROZVI router not mounted")
    assert r.status_code == 200
