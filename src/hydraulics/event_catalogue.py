"""
Minimal event catalogue helpers for flood validation workflows.

Users supply event metadata and observation files; nothing is invented.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, Sequence

from src.hydraulics.validate_depth import HighWaterMark


@dataclass
class FloodEventRecord:
    event_id: str
    start_date: str
    end_date: str
    aoi_id: str = ""
    name: str = ""
    notes: str = ""
    rainfall_source: str = ""
    observation_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def load_high_water_marks_csv(path: str | Path) -> list[HighWaterMark]:
    """
    CSV columns (header required):
      x, y, depth_m
    optional: mark_id, source, notes
    """
    path = Path(path)
    marks: list[HighWaterMark] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            marks.append(
                HighWaterMark(
                    x=float(row["x"]),
                    y=float(row["y"]),
                    depth_m=float(row["depth_m"]),
                    mark_id=str(row.get("mark_id") or f"hwm_{i}"),
                    source=str(row.get("source") or path.name),
                    notes=str(row.get("notes") or ""),
                )
            )
    return marks


def save_validation_report(
    report: Any,
    path: str | Path,
    *,
    write_docx: bool = True,
) -> Path:
    """Save validation JSON; optionally also write a sibling .docx Word report."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict() if hasattr(report, "to_dict") else report
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    if write_docx:
        try:
            from src.reporting.docx_report import write_validation_report_docx
            docx_path = path.with_suffix(".docx")
            write_validation_report_docx(report, docx_path)
        except Exception as exc:
            from src.utils import get_logger
            get_logger(__name__).warning("Validation Word report skipped: %s", exc)
    return path
