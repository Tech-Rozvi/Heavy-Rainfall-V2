"""
Asset and address schemas.

Assets are user-supplied (CSV, GeoJSON) or fetched optionally from OSM.
No synthetic assets are invented for production claims.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, Sequence, Union

from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class Asset:
    """Single addressable asset or location of interest."""
    asset_id: str
    x: float
    y: float
    name: Optional[str] = None
    asset_type: str = "unknown"  # building | road_segment | facility | address | other
    address: Optional[str] = None
    attributes: dict = field(default_factory=dict)
    crs: str = "EPSG:4326"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AssetCollection:
    assets: list[Asset] = field(default_factory=list)
    source: str = "user"
    crs: str = "EPSG:4326"
    notes: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.assets)

    def to_dict(self) -> dict:
        return {
            "n_assets": len(self.assets),
            "source": self.source,
            "crs": self.crs,
            "notes": self.notes,
            "assets": [a.to_dict() for a in self.assets],
        }


def load_assets_csv(
    path: Union[str, Path],
    *,
    id_col: str = "asset_id",
    x_col: str = "x",
    y_col: str = "y",
    name_col: str = "name",
    type_col: str = "asset_type",
    address_col: str = "address",
    crs: str = "EPSG:4326",
) -> AssetCollection:
    """
    Load assets from CSV.

    Required columns: asset_id (or id), x (or lon), y (or lat).
    """
    path = Path(path)
    assets: list[Asset] = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            try:
                aid = str(row.get(id_col) or row.get("id") or f"asset_{i}")
                x = float(row.get(x_col) or row.get("lon") or row.get("longitude"))
                y = float(row.get(y_col) or row.get("lat") or row.get("latitude"))
                assets.append(Asset(
                    asset_id=aid,
                    x=x,
                    y=y,
                    name=row.get(name_col) or row.get("name"),
                    asset_type=str(row.get(type_col) or row.get("type") or "unknown"),
                    address=row.get(address_col),
                    attributes={k: v for k, v in row.items()
                                if k not in (id_col, x_col, y_col, name_col, type_col, address_col)},
                    crs=crs,
                ))
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping asset row %s: %s", i, exc)
    return AssetCollection(assets=assets, source=str(path), crs=crs)


def load_assets_geojson(
    path: Union[str, Path],
    *,
    crs: str = "EPSG:4326",
) -> AssetCollection:
    """Load Point features from a GeoJSON file as assets."""
    path = Path(path)
    data = json.loads(path.read_text())
    features = data.get("features") or []
    assets: list[Asset] = []
    for i, feat in enumerate(features):
        geom = feat.get("geometry") or {}
        props = feat.get("properties") or {}
        if geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        assets.append(Asset(
            asset_id=str(props.get("asset_id") or props.get("id") or f"asset_{i}"),
            x=float(coords[0]),
            y=float(coords[1]),
            name=props.get("name"),
            asset_type=str(props.get("asset_type") or props.get("type") or "unknown"),
            address=props.get("address"),
            attributes={k: v for k, v in props.items()
                        if k not in ("asset_id", "id", "name", "asset_type", "type", "address")},
            crs=crs,
        ))
    notes = []
    if not assets:
        notes.append("No Point features found in GeoJSON.")
    return AssetCollection(assets=assets, source=str(path), crs=crs, notes=notes)


def assets_from_coordinates(
    points: Sequence[tuple[float, float]],
    *,
    crs: str = "EPSG:4326",
    asset_type: str = "address",
) -> AssetCollection:
    """Build an AssetCollection from a list of (x, y) coordinates."""
    assets = [
        Asset(asset_id=f"pt_{i}", x=float(x), y=float(y), asset_type=asset_type, crs=crs)
        for i, (x, y) in enumerate(points)
    ]
    return AssetCollection(assets=assets, source="coordinates", crs=crs)
