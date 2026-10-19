"""
Gauge / known-event validation harness.

Accepts user-supplied or bundled station tables and compares model fields
or series against observations.  Does not fabricate gauges.

Station CSV schema (flexible):
  station_id, x, y, observed_value [, source] [, observed_event]
  or time series long format: station_id, time, value

Coordinates may be projected or geographic; caller supplies CRS context.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

from src.eprf.validation.metrics import evaluate_precipitation, evaluate_extremes
from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class StationRecord:
    station_id: str
    x: float
    y: float
    observed_value: float
    source: str = "unknown"
    observed_event: Optional[int] = None


@dataclass
class GaugeValidationReport:
    n_stations: int
    metrics: dict[str, float]
    extreme_metrics: dict[str, float]
    by_source: dict[str, dict[str, float]]
    notes: list[str] = field(default_factory=list)
    station_residuals: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def load_station_csv(path: Union[str, Path]) -> list[StationRecord]:
    """Load station point observations from CSV."""
    path = Path(path)
    rows: list[StationRecord] = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                rows.append(StationRecord(
                    station_id=str(r.get("station_id", r.get("id", ""))),
                    x=float(r["x"] if "x" in r else r.get("lon", r.get("longitude"))),
                    y=float(r["y"] if "y" in r else r.get("lat", r.get("latitude"))),
                    observed_value=float(r.get("observed_value", r.get("value"))),
                    source=str(r.get("source", "unknown")),
                    observed_event=int(r["observed_event"]) if r.get("observed_event") not in (None, "") else None,
                ))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping station row: %s (%s)", r, exc)
    return rows


def extract_at_points(
    field_2d: np.ndarray,
    stations: list[StationRecord],
    *,
    transform: Optional[Any] = None,
    bounds: Optional[tuple[float, float, float, float]] = None,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """
    Sample a 2-D field at station locations.

    If transform (affine) is provided, uses row/col from world coords.
    Else if bounds=(minx,miny,maxx,maxy), assumes regular grid.
    Else treats station x,y as column,row indices (legacy synthetic layout).
    """
    arr = np.asarray(field_2d, dtype="float64")
    if arr.ndim != 2:
        raise ValueError("field_2d must be 2-D")
    ny, nx = arr.shape
    obs = []
    sim = []
    ids = []
    notes = []

    for st in stations:
        if transform is not None:
            try:
                import rasterio.transform
                col, row = ~transform * (st.x, st.y)
                r, c = int(round(row)), int(round(col))
            except Exception:
                notes.append(f"transform failed for {st.station_id}")
                continue
        elif bounds is not None:
            minx, miny, maxx, maxy = bounds
            if maxx == minx or maxy == miny:
                continue
            c = int(round((st.x - minx) / (maxx - minx) * (nx - 1)))
            r = int(round((maxy - st.y) / (maxy - miny) * (ny - 1)))
        else:
            # Synthetic / index mode used by bundled stations.csv
            c = int(round(st.x / max(arr.shape[1], 1))) if abs(st.x) > nx else int(round(st.x))
            r = int(round(abs(st.y) / max(arr.shape[0], 1))) if abs(st.y) > ny else int(round(st.y))
            # Clamp heuristic for large projected coords into grid
            if abs(st.x) > nx or abs(st.y) > ny:
                c = int(np.clip(st.x / 5000.0, 0, nx - 1))
                r = int(np.clip(abs(st.y) / 5000.0, 0, ny - 1))

        if r < 0 or c < 0 or r >= ny or c >= nx:
            continue
        val = arr[r, c]
        if not np.isfinite(val):
            continue
        obs.append(st.observed_value)
        sim.append(float(val))
        ids.append(st.station_id)

    return np.asarray(obs), np.asarray(sim), ids


def validate_field_against_stations(
    field_2d: np.ndarray,
    stations: list[StationRecord],
    *,
    transform: Optional[Any] = None,
    bounds: Optional[tuple[float, float, float, float]] = None,
    extreme_percentile: float = 90.0,
) -> GaugeValidationReport:
    """Compare a 2-D modelled field to station point values."""
    notes = []
    if not stations:
        return GaugeValidationReport(
            n_stations=0, metrics={}, extreme_metrics={}, by_source={},
            notes=["No stations provided"],
        )

    # Overall
    obs, sim, ids = extract_at_points(field_2d, stations, transform=transform, bounds=bounds)
    if len(obs) < 3:
        notes.append(f"Only {len(obs)} extractable station pairs; metrics unstable.")
    metrics = evaluate_precipitation(obs, sim) if len(obs) else {}
    extreme_metrics = (
        evaluate_extremes(obs, sim, obs_percentile=extreme_percentile) if len(obs) >= 10 else {}
    )

    residuals = [
        {"station_id": ids[i], "obs": float(obs[i]), "sim": float(sim[i]),
         "residual": float(sim[i] - obs[i])}
        for i in range(len(ids))
    ]

    # By source
    by_source: dict[str, dict[str, float]] = {}
    sources = {st.source for st in stations}
    for src in sources:
        subset = [st for st in stations if st.source == src]
        o2, s2, _ = extract_at_points(field_2d, subset, transform=transform, bounds=bounds)
        if len(o2) >= 2:
            by_source[src] = evaluate_precipitation(o2, s2)

    notes.append(
        "Station coordinates in bundled data may be synthetic/projected; "
        "treat metrics as harness demonstration unless CRS/alignment is verified."
    )
    return GaugeValidationReport(
        n_stations=len(obs),
        metrics=metrics,
        extreme_metrics=extreme_metrics,
        by_source=by_source,
        notes=notes,
        station_residuals=residuals,
    )


def validate_series_pair(
    obs_series: np.ndarray,
    model_series: np.ndarray,
    *,
    extreme_percentile: float = 95.0,
) -> dict[str, Any]:
    """Validate aligned 1-D observation vs model series (e.g. one station)."""
    metrics = evaluate_precipitation(obs_series, model_series)
    extreme = evaluate_extremes(obs_series, model_series, obs_percentile=extreme_percentile)
    return {"metrics": metrics, "extreme_metrics": extreme}
