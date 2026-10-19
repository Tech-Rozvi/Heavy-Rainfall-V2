"""
Formal data contracts between Rainfall, Climate, and Hydraulics modules.

Every payload carries provenance so that no consumer can mistake a projection
for an observation or a rainfall depth for a flood depth.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class ModuleOutputMeta:
    """Common metadata attached to every inter-module payload."""
    aoi_id: str
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_version: str = "8.2.0"
    module: str = ""
    crs: str = "EPSG:4326"
    units: dict = field(default_factory=dict)
    scenario: Optional[str] = None
    return_period_years: Optional[int] = None
    confidence: Optional[str] = None
    data_kind: str = "estimated"   # observed | estimated | modelled | projected | bias_corrected | hydraulically_simulated
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RainfallForcing:
    """
    Structured rainfall input for the hydraulics module.

    The hydraulics module must consume this (or an equivalent schema)
    and must never be given a bare susceptibility score as if it were rainfall.
    """
    meta: ModuleOutputMeta
    total_depth_mm: float
    duration_hours: float
    peak_intensity_mm_h: float
    hyetograph_mm: list[float]
    timestep_hours: float
    temporal_pattern: str
    spatial_field: Optional[Any] = None   # optional 2-D array or path
    ensemble_members: Optional[list[dict]] = None
    return_level_source: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d

    def assert_not_flood_depth(self) -> None:
        """Guard: this object is rainfall, not flood depth."""
        assert self.meta.data_kind != "hydraulically_simulated", (
            "RainfallForcing must not carry hydraulically_simulated data_kind"
        )


@dataclass
class ClimateAdjustment:
    """
    Transparent climate-change adjustment factors / fields.

    Explicitly records whether the method is delta_change, quantile_delta_mapping,
    bias_corrected_delta, or external dynamical downscaling product.
    """
    meta: ModuleOutputMeta
    method: str                    # delta_change | quantile_delta_mapping | bias_corrected_delta | cordex_product | wrf_product
    ssp: Optional[str]
    horizon_year: Optional[int]
    baseline_period: tuple[int, int]
    future_period: tuple[int, int]
    delta_mean_frac: Optional[float] = None
    delta_extreme_frac: Optional[float] = None
    ensemble_percentiles: Optional[dict[str, float]] = None  # P10, P50, P90, ...
    source_gcms: Optional[list[str]] = None
    source_rcms: Optional[list[str]] = None
    is_dynamical_downscaling: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d


@dataclass
class HydraulicResult:
    """
    Results returned *from* the hydraulics module back to the risk platform.

    The rainfall module never fabricates these fields.

    Validation status
    -----------------
    ``validation_status`` must be one of:
      provisional | event_validated | research_only
    Depth products are **provisional** until compared to observed flood
    events.  Consumers must not treat provisional depths as regulatory
    design flood surfaces without further validation.
    """
    meta: ModuleOutputMeta
    max_depth_m: Optional[Any] = None
    water_surface_elevation_m: Optional[Any] = None
    flood_extent: Optional[Any] = None
    velocity_m_s: Optional[Any] = None
    duration_h: Optional[Any] = None
    hazard_class: Optional[Any] = None
    forcing_aoi_id: Optional[str] = None
    forcing_return_period: Optional[int] = None
    validation_status: str = "provisional"
    validation_notes: list[str] = field(default_factory=list)
    product_labels: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.validation_notes and self.validation_status == "provisional":
            self.validation_notes = [
                "Flood depth products are PROVISIONAL until validated against "
                "observed flood events for this domain.",
            ]
        if not self.product_labels:
            self.product_labels = {
                "max_depth_m": "provisional_flood_depth",
                "flood_extent": "provisional_inundation_extent",
            }
        # Ensure meta never claims rainfall
        if self.meta.data_kind not in (
            "hydraulically_simulated",
            "modelled",
            "diagnostic",
        ):
            self.meta.data_kind = "hydraulically_simulated"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d

    def is_provisional(self) -> bool:
        return self.validation_status == "provisional"
