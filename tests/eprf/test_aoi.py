"""Tests for universal AOI ingestion."""
import json
import tempfile
from pathlib import Path

import pytest

from src.eprf.aoi.ingest import ingest_aoi
from src.eprf.aoi.point import point_to_aoi, PointMode
from src.eprf.aoi.diagnostics import aoi_diagnostic_report


def test_bbox_aoi():
    aoi = ingest_aoi(bbox=(30.0, -18.0, 32.0, -16.0), crs="EPSG:4326")
    assert aoi.geometry_type in ("Polygon", "MultiPolygon")
    assert aoi.crs_confidence == "user_supplied"
    assert aoi.area_km2 is not None and aoi.area_km2 > 0
    assert len(aoi.aoi_id) == 16


def test_point_with_buffer():
    aoi = point_to_aoi(31.05, -17.83, crs="EPSG:4326", mode=PointMode.BUFFER, buffer_km=10)
    assert aoi.point_mode == "buffer"
    assert aoi.buffer_radius_km == 10
    assert aoi.user_coordinate == (31.05, -17.83)
    assert aoi.area_km2 is not None and aoi.area_km2 > 0


def test_point_missing_crs_geographic_inference():
    aoi = point_to_aoi(31.05, -17.83)  # no CRS; should infer 4326 with low confidence
    assert aoi.crs_confidence == "inferred_low"
    assert any("inferred" in w.lower() or "EPSG:4326" in w for w in aoi.warnings)


def test_point_projected_requires_crs():
    with pytest.raises(ValueError, match="CRS is required"):
        point_to_aoi(500000, 8100000)  # clearly projected, no CRS


def test_geojson_file(tmp_path):
    gj = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[30, -18], [32, -18], [32, -16], [30, -16], [30, -18]]],
            },
        }],
    }
    path = tmp_path / "test.geojson"
    path.write_text(json.dumps(gj))
    aoi = ingest_aoi(source=path, crs="EPSG:4326")
    assert aoi.source_format in ("geojson", "json")
    assert aoi.n_features >= 1


def test_diagnostic_report():
    aoi = ingest_aoi(bbox=(30, -18, 32, -16), crs="EPSG:4326")
    report = aoi_diagnostic_report(aoi, station_count_nearby=3)
    assert report["status"] in ("ok", "warning")
    assert "aoi_id" in report
    assert "recommendation" in report
