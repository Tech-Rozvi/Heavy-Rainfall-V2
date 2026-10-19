"""Phase 8: capability docs exist; e2e workflow imports and runs."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_capability_matrix_exists_and_has_statuses():
    text = (ROOT / "docs" / "CAPABILITY_MATRIX.md").read_text()
    for token in ("IMPLEMENTED", "PROVISIONAL", "NOT YET IMPLEMENTED", "Flood depth"):
        assert token in text


def test_scientific_claims_exists():
    text = (ROOT / "docs" / "SCIENTIFIC_CLAIMS.md").read_text()
    assert "cannot" in text.lower()
    assert "RainfallForcing" in text or "rainfall" in text.lower()


def test_phase8_workflow_runs():
    # Execute as module path to keep coverage of the demo script
    import runpy
    script = ROOT / "examples" / "workflow_phase8_end_to_end.py"
    assert script.exists()
    # runpy will execute main via __main__ guard only if name is __main__
    # Call main() directly instead
    import importlib.util
    spec = importlib.util.spec_from_file_location("wf8", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rc = mod.main()
    assert rc == 0
    summary = ROOT / "outputs" / "phase8_demo" / "summary.json"
    assert summary.exists()
    import json
    data = json.loads(summary.read_text())
    assert data["chain"]["overall_confidence"] in (
        "Very low", "Low", "Moderate", "High", "Not quantified"
    )
    assert data["hydraulics_validation_status"] == "provisional"
