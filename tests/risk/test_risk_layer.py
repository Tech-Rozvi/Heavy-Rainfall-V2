"""Phase 6 tests: assets, point query, roads, risk snapshot."""
import numpy as np
import pytest

from src.risk.assets import (
    Asset,
    AssetCollection,
    load_assets_csv,
    assets_from_coordinates,
)
from src.risk.query import query_point_hazard, query_assets_hazard
from src.risk.report import build_risk_snapshot


def test_load_example_assets_csv():
    coll = load_assets_csv("data/assets/example_assets.csv")
    assert len(coll) == 3
    assert coll.assets[0].asset_id == "A001"


def test_assets_from_coordinates():
    coll = assets_from_coordinates([(31.0, -17.8), (31.1, -17.9)])
    assert len(coll) == 2
    assert coll.assets[0].asset_type == "address"


def test_query_point_with_bounds():
    field = np.arange(100.0).reshape(10, 10)
    # bounds map x from 0..9, y from 9..0 visually
    bounds = (0.0, 0.0, 9.0, 9.0)
    r = query_point_hazard(4.0, 5.0, {"depth_m": field}, bounds=bounds)
    assert r.inside_grid
    assert "depth_m" in r.values
    assert r.hazard_validation_status == "provisional"


def test_query_assets_batch():
    field = np.full((20, 20), 0.3)
    coll = assets_from_coordinates([(5, 5), (10, 10), (100, 100)])
    results = query_assets_hazard(coll, {"depth_m": field})
    assert len(results) == 3
    # first two should be inside as col/row indices
    assert results[0].inside_grid
    assert results[0].values.get("depth_m") == pytest.approx(0.3)


def test_risk_snapshot_disclaimers():
    coll = load_assets_csv("data/assets/example_assets.csv")
    field = np.ones((50, 50)) * 0.4
    results = query_assets_hazard(
        AssetCollection(assets=[
            Asset("t1", 10, 10),
            Asset("t2", 20, 20),
        ]),
        {"flood_depth_m": field},
        hazard_validation_status="provisional",
    )
    snap = build_risk_snapshot(
        "demo_aoi",
        hazard_layers={"flood_depth_m": field},
        hazard_validation_status="provisional",
        asset_results=results,
        building_exposure={"n_buildings": 2, "by_threshold": {"gt_0.15m": 1}},
    )
    d = snap.to_dict()
    assert d["hazard_products"]["validation_status"] == "provisional"
    assert any("not financial" in x.lower() or "not an insured" in x.lower()
               for x in d["disclaimers"])
    assert d["building_exposure"]["n_buildings"] == 2
    assert len(d["asset_results"]) == 2


def test_road_intersection_synthetic():
    geopandas = pytest.importorskip("geopandas")
    from shapely.geometry import LineString
    from rasterio.transform import from_origin
    from src.risk.roads import road_hazard_intersection

    # 10x10 depth grid, western half wet
    depth = np.zeros((10, 10))
    depth[:, :5] = 0.6
    transform = from_origin(0.0, 10.0, 1.0, 1.0)  # origin top-left
    roads = geopandas.GeoDataFrame(
        {"id": [1]},
        geometry=[LineString([(0.5, 5.0), (9.5, 5.0)])],
        crs="EPSG:3857",
    )
    report = road_hazard_intersection(
        depth, roads, transform, thresholds_m=(0.15, 0.5),
        hazard_validation_status="provisional",
    )
    assert report.n_segments >= 1
    assert report.total_length_m > 0
    assert report.exposed_length_by_threshold_m["gt_0.15m"] > 0
    assert report.hazard_validation_status == "provisional"
