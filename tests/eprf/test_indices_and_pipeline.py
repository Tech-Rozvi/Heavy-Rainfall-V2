"""Tests for ETCCDI indices and the EPRF pipeline on synthetic data."""
import numpy as np
import pytest
from pathlib import Path

from src.eprf.features.indices import compute_etccdi_indices
from src.eprf.pipeline import run_eprf
from src.utils import load_config


def test_etccdi_keys_and_shapes():
    rng = np.random.default_rng(0)
    daily = rng.exponential(3, size=(400, 5, 5))
    idx = compute_etccdi_indices(daily)
    for key in ("map_mm", "rx1day", "rx5day", "r95p", "r10mm", "cdd", "cwd"):
        assert key in idx
        assert idx[key].shape == (5, 5)
        assert np.all(np.isfinite(idx[key]) | np.isnan(idx[key]))


def test_pipeline_runs_on_synthetic(tmp_path):
    rng = np.random.default_rng(42)
    # 12 years of daily data on a small grid
    daily = rng.exponential(4.0, size=(365 * 12, 6, 6)).astype("float32")
    cfg = {
        "project": {"version": "7.0.0", "random_seed": 42},
        "extremes": {
            "return_periods": [10, 50, 100],
            "n_bootstrap": 20,   # keep test fast
            "ci_level": 0.90,
        },
        "uncertainty": {},
        "paths": {"output_dir": str(tmp_path)},
    }
    result = run_eprf(daily, cfg, output_dir=tmp_path)
    assert "indices" in result
    assert "return_levels" in result
    assert "rl_100" in result["return_levels"]
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "provenance.json").exists()
    assert result["summary"]["rl_100_mean"] > 0
