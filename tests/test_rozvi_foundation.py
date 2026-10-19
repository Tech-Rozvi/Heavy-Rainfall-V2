"""Phase 2 foundation tests: config, provenance, QC, orchestrator AOI."""
import numpy as np
import pytest

from src.rozvi import __version__, __platform_name__, __eprf_version__
from src.rozvi.config import load_rozvi_config, validate_config
from src.rozvi.provenance import build_provenance, Provenance
from src.rozvi.qc import qc_precipitation_array, qc_crs_consistency
from src.rozvi.orchestrator import resolve_aoi, qc_and_flag_precip, write_run_manifest


def test_versions():
    assert __platform_name__ == "ROZVI"
    assert __version__ >= "0.10.0"
    assert __eprf_version__.startswith("8.")


def test_load_rozvi_config():
    cfg = load_rozvi_config("config/rozvi.yaml")
    assert cfg["platform"]["name"] == "ROZVI"
    assert "extremes" in cfg
    assert cfg["scientific_options"]["never_present_susceptibility_as_flood_hazard"] is True


def test_config_rejects_delta_as_dynamical():
    cfg = {
        "climate": {"method": "relative_delta", "is_dynamical_downscaling": True},
        "platform": {},
        "data_acquisition": {},
        "scientific_options": {},
    }
    from src.rozvi.config import _normalize
    cfg = _normalize(cfg)
    issues = validate_config(cfg)
    assert any("dynamical" in m.lower() for m in issues)


def test_provenance_roundtrip(tmp_path):
    p = build_provenance(
        aoi_id="abc",
        product="test",
        data_kind="estimated",
        parameters={"T": 100},
        config={"a": 1},
    )
    p.add_dataset(name="chirps", source="UCSB", role="input")
    p.add_step("gev_fit")
    path = tmp_path / "prov.json"
    p.to_json(path)
    assert path.exists()
    assert p.config_hash is not None


def test_qc_detects_negatives_and_extremes():
    arr = np.array([0.0, 5.0, -1.0, 900.0, np.nan])
    report = qc_precipitation_array(arr, max_daily_mm=800.0)
    codes = {f.code for f in report.flags}
    assert "negative_values" in codes
    assert "extreme_values" in codes
    assert report.n_errors >= 1


def test_qc_all_nan_is_error():
    report = qc_precipitation_array(np.array([np.nan, np.nan]))
    assert report.passed is False
    assert any(f.code == "all_nan" for f in report.flags)


def test_qc_crs():
    r = qc_crs_consistency("EPSG:4326", "EPSG:4326")
    assert r.passed
    r2 = qc_crs_consistency(None, None)
    assert r2.passed is False


def test_resolve_aoi_bbox():
    aoi, diag = resolve_aoi(bbox=(30.0, -18.0, 32.0, -16.0), crs="EPSG:4326")
    assert aoi.aoi_id
    assert diag["status"] in ("ok", "warning")


def test_write_manifest(tmp_path):
    aoi, diag = resolve_aoi(bbox=(30.0, -18.0, 31.0, -17.0), crs="EPSG:4326")
    qc = qc_and_flag_precip(np.random.default_rng(0).exponential(3, size=100))
    path = write_run_manifest(tmp_path, aoi=aoi, diagnostic=diag, qc_report=qc)
    assert path.exists()
    import json
    data = json.loads(path.read_text())
    assert "provenance" in data
    assert data["aoi"]["aoi_id"] == aoi.aoi_id
