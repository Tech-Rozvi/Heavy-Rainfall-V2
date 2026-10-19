"""
Unified configuration loader for ROZVI.

Preference order:
1. Explicit path passed by caller
2. config/rozvi.yaml (authoritative)
3. config/eprf/eprf_config.yaml (legacy EPRF)
4. config/default_config.yaml
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from src.utils import get_logger

logger = get_logger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_SEARCH = [
    _ROOT / "config" / "rozvi.yaml",
    _ROOT / "config" / "eprf" / "eprf_config.yaml",
    _ROOT / "config" / "default_config.yaml",
    _ROOT / "config" / "config.yaml",
]


def load_rozvi_config(path: Optional[str | Path] = None) -> dict[str, Any]:
    """Load and lightly validate the unified ROZVI configuration."""
    if path is not None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config not found: {p}")
        cfg = yaml.safe_load(p.read_text()) or {}
        logger.info("Loaded config from %s", p)
    else:
        cfg = {}
        for candidate in _SEARCH:
            if candidate.exists():
                cfg = yaml.safe_load(candidate.read_text()) or {}
                logger.info("Loaded config from %s", candidate)
                break
        if not cfg:
            logger.warning("No config file found; using empty defaults")

    cfg = _normalize(cfg)
    issues = validate_config(cfg)
    for msg in issues:
        logger.warning("Config validation: %s", msg)
    return cfg


def _normalize(cfg: dict) -> dict:
    """Ensure required top-level keys exist with safe defaults."""
    cfg.setdefault("platform", {})
    cfg["platform"].setdefault("name", "ROZVI")
    cfg["platform"].setdefault("version", "0.1.0")
    cfg["platform"].setdefault("random_seed", 42)

    cfg.setdefault("crs", {})
    cfg["crs"].setdefault("working", "EPSG:4326")

    cfg.setdefault("paths", {})
    cfg["paths"].setdefault("output_dir", "outputs")

    cfg.setdefault("data_acquisition", {})
    cfg["data_acquisition"].setdefault("allow_synthetic", False)

    cfg.setdefault("scientific_options", {})
    cfg["scientific_options"].setdefault("allow_synthetic_data", False)
    cfg["scientific_options"].setdefault(
        "never_present_susceptibility_as_flood_hazard", True
    )
    cfg["scientific_options"].setdefault(
        "never_present_delta_as_dynamical_downscaling", True
    )

    # Bridge legacy project/version keys used by older modules
    if "project" not in cfg:
        cfg["project"] = {
            "name": cfg["platform"].get("name", "ROZVI"),
            "version": cfg["platform"].get("version", "0.1.0"),
            "random_seed": cfg["platform"].get("random_seed", 42),
        }
    return cfg


def validate_config(cfg: dict) -> list[str]:
    """Return list of validation messages (empty if OK)."""
    issues = []
    if cfg.get("climate", {}).get("is_dynamical_downscaling") is True:
        method = str(cfg.get("climate", {}).get("method", ""))
        if "delta" in method.lower():
            issues.append(
                "climate.is_dynamical_downscaling=true is inconsistent with "
                f"method={method}; delta methods are not dynamical downscaling"
            )
    if cfg.get("data_acquisition", {}).get("allow_synthetic") and not cfg.get(
        "scientific_options", {}
    ).get("allow_synthetic_data"):
        issues.append(
            "data_acquisition.allow_synthetic=true but "
            "scientific_options.allow_synthetic_data=false"
        )
    return issues
