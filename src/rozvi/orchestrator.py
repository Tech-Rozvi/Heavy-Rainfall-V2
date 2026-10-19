"""
ROZVI Phase 2 orchestration helpers.

Wires EPRF AOI + QC + provenance into a single entry used by CLI/API.
Does not replace scientific engines; it coordinates them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Sequence, Union

import numpy as np

from src.rozvi.config import load_rozvi_config
from src.rozvi.provenance import build_provenance
from src.rozvi.qc import qc_precipitation_array, QCReport
from src.eprf.aoi.ingest import ingest_aoi, AOIRecord
from src.eprf.aoi.diagnostics import aoi_diagnostic_report
from src.utils import get_logger

logger = get_logger(__name__)


def resolve_aoi(
    *,
    source: Optional[Union[str, Path]] = None,
    bbox: Optional[Sequence[float]] = None,
    point: Optional[Sequence[float]] = None,
    crs: Optional[str] = None,
    buffer_km: Optional[float] = None,
    point_mode: str = "buffer",
    config: Optional[dict] = None,
) -> tuple[AOIRecord, dict]:
    """
    Ingest AOI and return (AOIRecord, diagnostic_report).
    """
    cfg = config or load_rozvi_config()
    aoi_cfg = cfg.get("aoi", {})
    if buffer_km is None:
        buffer_km = float(aoi_cfg.get("default_point_buffer_km", 10))
    if point is not None and point_mode is None:
        point_mode = aoi_cfg.get("default_point_mode", "buffer")

    aoi = ingest_aoi(
        source=source,
        bbox=bbox,
        point=point,
        crs=crs,
        buffer_km=buffer_km,
        point_mode=point_mode,
    )
    diag = aoi_diagnostic_report(aoi)
    if diag["status"] == "error":
        logger.error("AOI diagnostic status=error: %s", diag.get("warnings"))
    elif diag["status"] == "warning":
        logger.warning("AOI diagnostic warnings: %s", diag.get("warnings"))
    return aoi, diag


def qc_and_flag_precip(
    daily_precip: np.ndarray,
    *,
    config: Optional[dict] = None,
    name: str = "precipitation",
) -> QCReport:
    """Run precipitation QC using config thresholds."""
    cfg = config or load_rozvi_config()
    qc_cfg = cfg.get("qc", {})
    report = qc_precipitation_array(
        daily_precip,
        name=name,
        max_daily_mm=float(qc_cfg.get("precip_max_daily_mm", 800.0)),
        min_mm=float(qc_cfg.get("precip_min_mm", 0.0)),
        allow_nan=bool(qc_cfg.get("allow_nan", True)),
    )
    if not report.passed and qc_cfg.get("fail_on_error", False):
        raise ValueError(f"QC failed for {name}: {report.to_dict()}")
    return report


def write_run_manifest(
    output_dir: Path | str,
    *,
    aoi: AOIRecord,
    diagnostic: dict,
    qc_report: Optional[QCReport] = None,
    product: str = "rozvi_run",
    data_kind: str = "estimated",
    extra: Optional[dict] = None,
    config: Optional[dict] = None,
) -> Path:
    """Write provenance + AOI diagnostic + QC to output_dir/manifest.json."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    prov = build_provenance(
        aoi_id=aoi.aoi_id,
        product=product,
        data_kind=data_kind,
        crs=aoi.crs,
        config=config,
        confidence=aoi.crs_confidence,
        notes=list(aoi.warnings),
    )
    prov.add_step("aoi_ingestion")
    if qc_report is not None:
        prov.add_step(f"qc:{qc_report.summary}")
    manifest = {
        "provenance": prov.to_dict(),
        "aoi": aoi.to_dict(),
        "aoi_diagnostic": diagnostic,
        "qc": qc_report.to_dict() if qc_report else None,
        "extra": extra or {},
    }
    path = out / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=str))
    logger.info("Wrote run manifest to %s", path)
    return path
