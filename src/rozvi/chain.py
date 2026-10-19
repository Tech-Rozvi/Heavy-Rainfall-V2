"""
Full-chain uncertainty and provenance for ROZVI.

Chain
-----
rainfall / extremes → bias (optional) → hydrology → hydraulics → exposure/risk

Scientific rules
----------------
- A stage may report a quantitative interval only if that stage computed one
  (e.g. GEV bootstrap CI, or a user-supplied sensitivity ensemble).
- Downstream stages do **not** inherit a numerical CI they did not compute.
- Overall confidence is the **weakest quantified stage** (ordinal minimum).
- Hydraulic depth remains provisional unless event-validated.
- This module does **not** claim a full Monte Carlo propagation through the
  shallow-water solver.  ``claims_full_propagation`` is False unless the caller
  supplies an ensemble of end-to-end realisations and asks for empirical
  percentiles via ``empirical_interval``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Sequence

import numpy as np

from src.rozvi.provenance import Provenance, build_provenance

CONFIDENCE_ORDER = ("Very low", "Low", "Moderate", "High")
_RANK = {name: i for i, name in enumerate(CONFIDENCE_ORDER)}


def weakest_confidence(labels: Sequence[Optional[str]]) -> str:
    """Ordinal minimum among recognised confidence labels. Empty → Not quantified."""
    ranks = [_RANK[x] for x in labels if x in _RANK]
    if not ranks:
        return "Not quantified"
    return CONFIDENCE_ORDER[min(ranks)]


@dataclass
class StageUncertainty:
    """Uncertainty statement for one link in the chain."""
    stage: str
    confidence: str
    quantified: bool = False
    estimate: Optional[float] = None
    interval_low: Optional[float] = None
    interval_high: Optional[float] = None
    interval_level: Optional[float] = None
    units: Optional[str] = None
    validation_status: str = "not_validated"
    drivers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChainUncertainty:
    """Combined chain record. Overall confidence is the weakest link."""
    stages: list[StageUncertainty]
    overall_confidence: str
    weakest_stage: Optional[str]
    claims_full_propagation: bool = False
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.notes:
            self.notes = [
                "Overall confidence is the weakest quantified stage, not a "
                "joint probability.",
                "Numerical intervals apply only to the stage that computed them.",
            ]
        if self.claims_full_propagation:
            self.notes.append(
                "Full end-to-end propagation was requested; verify that the "
                "ensemble members are independent realisations, not resamples "
                "of a single fit."
            )

    def to_dict(self) -> dict:
        return {
            "stages": [s.to_dict() for s in self.stages],
            "overall_confidence": self.overall_confidence,
            "weakest_stage": self.weakest_stage,
            "claims_full_propagation": self.claims_full_propagation,
            "notes": self.notes,
        }

    def stage(self, name: str) -> Optional[StageUncertainty]:
        for s in self.stages:
            if s.stage == name:
                return s
        return None


def build_chain(stages: Sequence[StageUncertainty]) -> ChainUncertainty:
    """Assemble a chain and set overall confidence to the weakest quantified stage."""
    quantified = [s for s in stages if s.confidence in _RANK]
    if not quantified:
        return ChainUncertainty(
            stages=list(stages),
            overall_confidence="Not quantified",
            weakest_stage=None,
        )
    worst = min(quantified, key=lambda s: _RANK[s.confidence])
    return ChainUncertainty(
        stages=list(stages),
        overall_confidence=worst.confidence,
        weakest_stage=worst.stage,
    )


def stage_from_return_period(result: Any) -> StageUncertainty:
    """Map a ReturnPeriodResult (or duck-typed equivalent) onto a rainfall stage."""
    return StageUncertainty(
        stage="rainfall_extremes",
        confidence=str(getattr(result, "confidence", "Not quantified")),
        quantified=True,
        estimate=float(result.estimate_mm),
        interval_low=float(result.ci_lower_mm),
        interval_high=float(result.ci_upper_mm),
        interval_level=float(result.ci_level),
        units=getattr(result, "units", "mm"),
        validation_status="statistical_fit",
        drivers=[
            f"n_years={getattr(result, 'n_years', '?')}",
            f"extrapolation_ratio={getattr(result, 'extrapolation_ratio', '?')}",
            f"exceeds_record={getattr(result, 'exceeds_record', '?')}",
        ],
        notes=[str(getattr(result, "confidence_rationale", ""))],
    )


def stage_from_bias(method: Optional[str], *, n_cal: Optional[int] = None, holdout: bool = True) -> StageUncertainty:
    """Bias correction does not by itself raise confidence above Low unless hold-out skill is shown."""
    notes = []
    conf = "Low"
    if not holdout:
        conf = "Very low"
        notes.append("Bias method applied without temporal hold-out; leakage risk.")
    if n_cal is not None and n_cal < 30:
        conf = "Very low"
        notes.append(f"Calibration sample n={n_cal} is short.")
    return StageUncertainty(
        stage="bias_correction",
        confidence=conf,
        quantified=False,
        validation_status="benchmarked" if holdout else "not_validated",
        drivers=[f"method={method or 'none'}", f"n_cal={n_cal}"],
        notes=notes or ["Hold-out benchmark required before treating bias correction as skill."],
    )


def stage_from_hydrology(
    *,
    method: str,
    peak_m3s: Optional[float] = None,
    sensitivity_peaks_m3s: Optional[Sequence[float]] = None,
) -> StageUncertainty:
    """
    Hydrology uncertainty.

    A single CN/UH run is **not** a confidence interval.  If the caller supplies
    a sensitivity ensemble (e.g. CN ± range), the min/max is reported as a
    scenario envelope, not a probabilistic CI.
    """
    peaks = None
    if sensitivity_peaks_m3s is not None:
        peaks = [float(p) for p in sensitivity_peaks_m3s if np.isfinite(p)]
    quantified = bool(peaks) and len(peaks) >= 2
    low = min(peaks) if quantified else None
    high = max(peaks) if quantified else None
    notes = [
        "SCS-CN and triangular unit hydrograph are not regionally calibrated here.",
    ]
    if quantified:
        notes.append(
            "Interval is a sensitivity envelope (min/max of supplied runs), "
            "not a confidence interval."
        )
    else:
        notes.append("No parameter sensitivity supplied; peak discharge uncertainty not quantified.")
    return StageUncertainty(
        stage="hydrology",
        confidence="Low",
        quantified=quantified,
        estimate=float(peak_m3s) if peak_m3s is not None else None,
        interval_low=low,
        interval_high=high,
        interval_level=None,
        units="m3/s",
        validation_status="not_validated",
        drivers=[f"method={method}", f"n_sensitivity={0 if not peaks else len(peaks)}"],
        notes=notes,
    )


def stage_from_hydraulics(*, validation_status: str = "provisional", max_depth_m: Optional[float] = None) -> StageUncertainty:
    """Depth products stay provisional; no fabricated depth CI.

    Event-validated (caller-asserted) is Moderate at best — this module does
    not audit the events.  Anything else is Very low.
    """
    confidence = "Moderate" if validation_status == "event_validated" else "Very low"
    return StageUncertainty(
        stage="hydraulics",
        confidence=confidence,
        quantified=False,
        estimate=max_depth_m,
        units="m",
        validation_status=validation_status,
        drivers=[f"validation_status={validation_status}"],
        notes=[
            "No event validation in this repository."
            if validation_status != "event_validated"
            else "Marked event-validated by caller; this module does not verify the events.",
            "Depth confidence interval is not computed (no SWE ensemble).",
        ],
    )


def stage_from_exposure(*, hazard_validation_status: str = "provisional") -> StageUncertainty:
    """Exposure inherits hazard status and adds no new quantitative uncertainty."""
    return StageUncertainty(
        stage="exposure",
        confidence="Very low" if hazard_validation_status != "event_validated" else "Low",
        quantified=False,
        validation_status=hazard_validation_status,
        drivers=["inherits hazard validation status"],
        notes=[
            "Physical exposure only; not financial risk.",
            "Does not reduce uncertainty relative to the hazard layer.",
        ],
    )


def empirical_interval(samples: Sequence[float], level: float = 0.9) -> tuple[float, float, float]:
    """
    Empirical central interval from end-to-end ensemble members.

    Returns (p_low, p_high, level).  This is the only path that may set
    ``claims_full_propagation=True``, and only if the caller asserts the
    samples are full-chain realisations.
    """
    x = np.asarray(list(samples), dtype="float64")
    x = x[np.isfinite(x)]
    if len(x) < 5:
        raise ValueError("Need at least 5 finite ensemble members for an empirical interval")
    tail = (1.0 - level) / 2.0
    return float(np.quantile(x, tail)), float(np.quantile(x, 1.0 - tail)), float(level)


def chain_with_ensemble(
    stages: Sequence[StageUncertainty],
    ensemble_samples: Sequence[float],
    *,
    units: str,
    level: float = 0.9,
    full_chain: bool = False,
) -> ChainUncertainty:
    """
    Attach an empirical interval as its own stage.

    ``full_chain=True`` only if samples are end-to-end realisations
    (rainfall through the quantity of interest).  Default False.
    """
    low, high, lvl = empirical_interval(ensemble_samples, level=level)
    ens = StageUncertainty(
        stage="ensemble",
        confidence="Low",
        quantified=True,
        estimate=float(np.nanmean(np.asarray(ensemble_samples, dtype="float64"))),
        interval_low=low,
        interval_high=high,
        interval_level=lvl,
        units=units,
        validation_status="ensemble",
        drivers=[f"n={len(list(ensemble_samples))}", f"full_chain={full_chain}"],
        notes=[
            "Empirical percentile interval of supplied samples.",
            "Not a calibrated predictive interval unless the ensemble spans the dominant error sources.",
        ],
    )
    chain = build_chain([*stages, ens])
    chain.claims_full_propagation = bool(full_chain)
    if full_chain:
        chain.notes.append(
            "Caller asserted these samples are full-chain realisations. "
            "ROZVI does not independently verify that assertion."
        )
    return chain


def provenance_for_chain(
    chain: ChainUncertainty,
    *,
    aoi_id: str,
    product: str = "chain_uncertainty",
    data_kind: str = "diagnostic",
    config: Optional[dict] = None,
    extra_notes: Optional[list[str]] = None,
) -> Provenance:
    """Single provenance record listing every stage as a processing step."""
    prov = build_provenance(
        aoi_id=aoi_id,
        product=product,
        data_kind=data_kind,
        confidence=chain.overall_confidence,
        config=config,
        notes=list(chain.notes) + list(extra_notes or []),
        parameters={
            "weakest_stage": chain.weakest_stage,
            "claims_full_propagation": chain.claims_full_propagation,
            "n_stages": len(chain.stages),
        },
    )
    for stage in chain.stages:
        prov.add_step(
            f"{stage.stage}: confidence={stage.confidence}; "
            f"quantified={stage.quantified}; status={stage.validation_status}"
        )
    prov.add_dataset(name="chain_uncertainty", role="diagnostic", units="mixed")
    return prov
