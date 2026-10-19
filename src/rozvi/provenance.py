"""
Formal provenance records for every ROZVI / EPRF output.

A result is reproducible only if input datasets, configuration, model
version, and processing steps are recorded.  This module provides a
single dataclass used across rainfall, climate, and hydraulics outputs.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.rozvi import __eprf_version__, __platform_name__, __version__


@dataclass
class DatasetRef:
    """Reference to one input dataset."""
    name: str
    source: Optional[str] = None
    version: Optional[str] = None
    path: Optional[str] = None
    crs: Optional[str] = None
    spatial_resolution: Optional[str] = None
    temporal_resolution: Optional[str] = None
    units: Optional[str] = None
    role: str = "input"  # input | intermediate | reference


@dataclass
class Provenance:
    """
    Traceable metadata attached to every major output.

    data_kind must be one of:
      observed | estimated | modelled | projected | bias_corrected
      | hydraulically_simulated | diagnostic
    """
    aoi_id: str
    product: str
    data_kind: str
    platform_version: str = __version__
    eprf_version: str = __eprf_version__
    platform_name: str = __platform_name__
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    crs: str = "EPSG:4326"
    units: dict = field(default_factory=dict)
    datasets: list[DatasetRef] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    processing_steps: list[str] = field(default_factory=list)
    random_seed: Optional[int] = None
    scenario: Optional[str] = None
    return_period_years: Optional[int] = None
    confidence: Optional[str] = None
    software: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    config_hash: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.software:
            self.software = {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
            }

    def add_dataset(self, **kwargs: Any) -> None:
        self.datasets.append(DatasetRef(**kwargs))

    def add_step(self, description: str) -> None:
        self.processing_steps.append(description)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def to_json(self, path: Optional[Path | str] = None) -> str:
        text = json.dumps(self.to_dict(), indent=2, default=str)
        if path is not None:
            Path(path).write_text(text)
        return text

    @staticmethod
    def hash_config(cfg: dict) -> str:
        payload = json.dumps(cfg, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_provenance(
    aoi_id: str,
    product: str,
    data_kind: str,
    *,
    crs: str = "EPSG:4326",
    units: Optional[dict] = None,
    parameters: Optional[dict] = None,
    config: Optional[dict] = None,
    random_seed: Optional[int] = None,
    scenario: Optional[str] = None,
    return_period_years: Optional[int] = None,
    confidence: Optional[str] = None,
    notes: Optional[list[str]] = None,
) -> Provenance:
    """Factory with consistent defaults."""
    return Provenance(
        aoi_id=aoi_id,
        product=product,
        data_kind=data_kind,
        crs=crs,
        units=units or {},
        parameters=parameters or {},
        random_seed=random_seed,
        scenario=scenario,
        return_period_years=return_period_years,
        confidence=confidence,
        config_hash=Provenance.hash_config(config) if config else None,
        notes=list(notes or []),
    )
