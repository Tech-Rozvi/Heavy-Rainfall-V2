"""Phase 10: legacy susceptibility quarantine metadata."""
from src.rozvi.legacy import (
    SUSCEPTIBILITY_DISCLAIMER,
    is_legacy_susceptibility_metadata,
    susceptibility_product_metadata,
    warn_legacy_susceptibility,
)


def test_metadata_flags_not_flood_or_finance():
    meta = susceptibility_product_metadata()
    assert meta["is_flood_depth"] is False
    assert meta["is_return_level"] is False
    assert meta["is_financial_risk"] is False
    assert meta["product_label"] == "legacy_relative_susceptibility"
    assert "LEGACY" in meta["disclaimer"]
    assert is_legacy_susceptibility_metadata(meta)


def test_warn_does_not_raise():
    warn_legacy_susceptibility()


def test_disclaimer_mentions_not_depth():
    assert "Not flood depth" in SUSCEPTIBILITY_DISCLAIMER
