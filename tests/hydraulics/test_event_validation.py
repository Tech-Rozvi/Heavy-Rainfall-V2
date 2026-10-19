"""Event depth validation gates."""
import numpy as np
import pytest

from src.hydraulics.validate_depth import (
    HighWaterMark,
    evaluate_event_depth,
    compare_inundation_footprint,
)


def test_pass_with_good_marks():
    depth = np.full((20, 20), 0.5)
    marks = [
        HighWaterMark(x=5, y=5, depth_m=0.48, mark_id="a"),
        HighWaterMark(x=10, y=10, depth_m=0.52, mark_id="b"),
        HighWaterMark(x=15, y=8, depth_m=0.50, mark_id="c"),
    ]
    rep = evaluate_event_depth(depth, marks, event_id="e1", min_marks=3, max_mae_m=0.1)
    assert rep.passed
    assert rep.validation_status == "event_validated"
    assert rep.point_metrics["mae_m"] is not None


def test_fail_with_large_error():
    depth = np.full((20, 20), 1.5)
    marks = [
        HighWaterMark(x=5, y=5, depth_m=0.2, mark_id="a"),
        HighWaterMark(x=10, y=10, depth_m=0.2, mark_id="b"),
        HighWaterMark(x=15, y=8, depth_m=0.2, mark_id="c"),
    ]
    rep = evaluate_event_depth(depth, marks, event_id="e2", min_marks=3, max_mae_m=0.3)
    assert not rep.passed
    assert rep.validation_status == "provisional"


def test_fail_insufficient_marks():
    depth = np.ones((10, 10))
    marks = [HighWaterMark(x=1, y=1, depth_m=1.0)]
    rep = evaluate_event_depth(depth, marks, min_marks=3)
    assert not rep.passed


def test_footprint_csi():
    depth = np.zeros((10, 10))
    depth[2:8, 2:8] = 0.5
    obs = np.zeros((10, 10), dtype=bool)
    obs[2:8, 2:8] = True
    fp = compare_inundation_footprint(depth, obs, threshold_m=0.05)
    assert fp.csi == pytest.approx(1.0)
