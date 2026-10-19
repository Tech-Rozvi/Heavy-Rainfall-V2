"""Phase 7: weakest-link chain uncertainty and provenance."""
import pytest

from src.rozvi.chain import (
    StageUncertainty,
    build_chain,
    chain_with_ensemble,
    empirical_interval,
    provenance_for_chain,
    stage_from_bias,
    stage_from_exposure,
    stage_from_hydraulics,
    stage_from_hydrology,
    stage_from_return_period,
    weakest_confidence,
)
from src.rozvi import __version__


class _RP:
    estimate_mm = 80.0
    ci_lower_mm = 60.0
    ci_upper_mm = 110.0
    ci_level = 0.9
    confidence = "Low"
    n_years = 12
    extrapolation_ratio = 8.3
    exceeds_record = True
    confidence_rationale = "T exceeds record"
    units = "mm"


def test_weakest_link_ordinal():
    assert weakest_confidence(["High", "Low", "Moderate"]) == "Low"
    assert weakest_confidence([]) == "Not quantified"
    assert weakest_confidence(["Not quantified", None]) == "Not quantified"


def test_chain_overall_is_weakest_quantified_label():
    stages = [
        stage_from_return_period(_RP()),          # Low, quantified CI
        stage_from_bias("empirical_quantile_mapping", n_cal=80, holdout=True),  # Low
        stage_from_hydrology(method="curve_number", peak_m3s=12.0),  # Low, not a CI
        stage_from_hydraulics(validation_status="provisional", max_depth_m=0.4),  # Very low
        stage_from_exposure(hazard_validation_status="provisional"),  # Very low
    ]
    chain = build_chain(stages)
    assert chain.overall_confidence == "Very low"
    assert chain.weakest_stage in ("hydraulics", "exposure")
    assert chain.claims_full_propagation is False
    rain = chain.stage("rainfall_extremes")
    assert rain.quantified and rain.interval_low == 60.0
    hydro = chain.stage("hydraulics")
    assert hydro.quantified is False
    assert hydro.interval_low is None


def test_hydrology_sensitivity_is_envelope_not_ci():
    st = stage_from_hydrology(
        method="curve_number",
        peak_m3s=10.0,
        sensitivity_peaks_m3s=[8.0, 10.0, 14.0],
    )
    assert st.quantified is True
    assert st.interval_low == 8.0
    assert st.interval_high == 14.0
    assert st.interval_level is None
    assert any("not a confidence interval" in n for n in st.notes)


def test_bias_without_holdout_is_very_low():
    st = stage_from_bias("linear_scaling", n_cal=100, holdout=False)
    assert st.confidence == "Very low"


def test_short_calibration_downgrades_bias():
    st = stage_from_bias("empirical_quantile_mapping", n_cal=10, holdout=True)
    assert st.confidence == "Very low"


def test_empirical_interval_and_no_false_full_propagation():
    samples = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    low, high, level = empirical_interval(samples, level=0.8)
    assert low < high
    assert level == 0.8
    chain = chain_with_ensemble(
        [stage_from_return_period(_RP())],
        samples,
        units="mm",
        full_chain=False,
    )
    assert chain.claims_full_propagation is False
    assert chain.stage("ensemble").quantified is True


def test_full_chain_flag_is_caller_asserted_only():
    chain = chain_with_ensemble(
        [StageUncertainty(stage="rainfall_extremes", confidence="Moderate", quantified=True)],
        [5, 6, 7, 8, 9, 10],
        units="m3/s",
        full_chain=True,
    )
    assert chain.claims_full_propagation is True
    assert any("does not independently verify" in n for n in chain.notes)


def test_empirical_interval_rejects_tiny_sample():
    with pytest.raises(ValueError):
        empirical_interval([1, 2, 3])


def test_provenance_lists_every_stage():
    chain = build_chain([
        stage_from_return_period(_RP()),
        stage_from_hydraulics(),
    ])
    prov = provenance_for_chain(chain, aoi_id="aoi-1", config={"a": 1})
    assert prov.aoi_id == "aoi-1"
    assert prov.confidence == "Very low"
    assert prov.platform_version == __version__
    steps = " ".join(prov.processing_steps)
    assert "rainfall_extremes" in steps
    assert "hydraulics" in steps
    assert prov.config_hash


def test_event_validated_hydraulics_not_above_moderate():
    st = stage_from_hydraulics(validation_status="event_validated", max_depth_m=1.2)
    assert st.confidence == "Moderate"
    assert any("does not verify" in n for n in st.notes)
