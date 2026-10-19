"""Phase 11: packaging artefacts exist and document honesty boundaries."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_present_and_versioned():
    text = (ROOT / "Dockerfile").read_text()
    assert "ROZVI" in text or "rozvi" in text.lower()
    assert "0.10.0" in text
    assert "CMD" in text


def test_compose_and_makefile():
    assert (ROOT / "docker-compose.yml").exists()
    mk = (ROOT / "Makefile").read_text()
    assert "verify:" in mk
    assert "docker-build:" in mk


def test_reproducibility_doc_states_limits():
    text = (ROOT / "docs" / "REPRODUCIBILITY.md").read_text()
    assert "not" in text.lower()
    assert "Event-validated" in text or "event-validated" in text


def test_dockerignore_excludes_pycache():
    text = (ROOT / ".dockerignore").read_text()
    assert "__pycache__" in text
