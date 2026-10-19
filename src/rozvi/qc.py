"""
Automated data quality control.

Principles
----------
- Detect and flag; do not silently repair.
- Every correction must be explicit, configurable, logged, and quality-flagged.
- Prefer: raw → QC → flags → processed.

This module provides checks for arrays, time series, and CRS consistency.
It does not overwrite source data.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Sequence

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class QCFlag:
    code: str
    severity: str          # info | warning | error
    message: str
    n_affected: int = 0
    fraction_affected: float = 0.0


@dataclass
class QCReport:
    dataset_name: str
    n_checks: int = 0
    n_errors: int = 0
    n_warnings: int = 0
    flags: list[QCFlag] = field(default_factory=list)
    summary: str = "ok"
    passed: bool = True

    def add(self, flag: QCFlag) -> None:
        self.flags.append(flag)
        self.n_checks += 1
        if flag.severity == "error":
            self.n_errors += 1
            self.passed = False
            self.summary = "error"
        elif flag.severity == "warning" and self.summary == "ok":
            self.n_warnings += 1
            self.summary = "warning"
        elif flag.severity == "warning":
            self.n_warnings += 1

    def to_dict(self) -> dict:
        return asdict(self)


def qc_precipitation_array(
    arr: np.ndarray,
    *,
    name: str = "precipitation",
    max_daily_mm: float = 800.0,
    min_mm: float = 0.0,
    allow_nan: bool = True,
) -> QCReport:
    """
    QC checks for a precipitation array (1-D series or N-D cube).

    Flags:
    - all_nan / empty
    - negative values
    - extreme values above max_daily_mm
    - high missing fraction
    """
    report = QCReport(dataset_name=name)
    a = np.asarray(arr, dtype="float64")
    n = a.size
    if n == 0:
        report.add(QCFlag("empty", "error", "Array is empty", 0, 1.0))
        return report

    nan_mask = ~np.isfinite(a)
    n_nan = int(nan_mask.sum())
    frac_nan = n_nan / n
    if frac_nan == 1.0:
        report.add(QCFlag("all_nan", "error", "All values are non-finite", n_nan, 1.0))
        return report
    if frac_nan > 0.5:
        report.add(QCFlag(
            "high_missing", "warning",
            f"Missing/non-finite fraction = {frac_nan:.1%}",
            n_nan, frac_nan,
        ))
    elif n_nan > 0 and not allow_nan:
        report.add(QCFlag(
            "missing_values", "error",
            f"{n_nan} non-finite values (allow_nan=False)",
            n_nan, frac_nan,
        ))
    elif n_nan > 0:
        report.add(QCFlag(
            "missing_values", "info",
            f"{n_nan} non-finite values ({frac_nan:.1%})",
            n_nan, frac_nan,
        ))

    finite = a[np.isfinite(a)]
    n_neg = int((finite < min_mm).sum())
    if n_neg > 0:
        report.add(QCFlag(
            "negative_values", "error",
            f"{n_neg} values below {min_mm}",
            n_neg, n_neg / max(len(finite), 1),
        ))

    n_extreme = int((finite > max_daily_mm).sum())
    if n_extreme > 0:
        report.add(QCFlag(
            "extreme_values", "warning",
            f"{n_extreme} values above {max_daily_mm} mm (check units/outliers)",
            n_extreme, n_extreme / max(len(finite), 1),
        ))

    if report.n_checks == 0:
        report.n_checks = 1
        report.add(QCFlag("ok", "info", "No issues detected", 0, 0.0))

    logger.info("QC %s: %s (%d errors, %d warnings)", name, report.summary, report.n_errors, report.n_warnings)
    return report


def qc_crs_consistency(
    declared_crs: Optional[str],
    detected_crs: Optional[str],
    *,
    name: str = "crs",
) -> QCReport:
    """Flag CRS mismatches or missing CRS."""
    report = QCReport(dataset_name=name)
    if not declared_crs and not detected_crs:
        report.add(QCFlag("crs_missing", "error", "No CRS declared or detected", 1, 1.0))
    elif declared_crs and detected_crs and str(declared_crs) != str(detected_crs):
        report.add(QCFlag(
            "crs_mismatch", "warning",
            f"Declared CRS {declared_crs} != detected {detected_crs}",
            1, 1.0,
        ))
    else:
        report.add(QCFlag("crs_ok", "info", f"CRS = {declared_crs or detected_crs}", 0, 0.0))
    return report


def qc_time_series_gaps(
    timestamps: Sequence,
    *,
    name: str = "time_series",
    expected_delta=None,
) -> QCReport:
    """
    Detect large temporal gaps when timestamps are sortable.

    expected_delta: optional expected step (e.g. datetime.timedelta(days=1)).
    """
    report = QCReport(dataset_name=name)
    if len(timestamps) < 2:
        report.add(QCFlag("too_short", "warning", "Fewer than 2 timestamps", len(timestamps), 1.0))
        return report
    try:
        ts = sorted(timestamps)
        gaps = []
        for i in range(1, len(ts)):
            delta = ts[i] - ts[i - 1]
            if expected_delta is not None and delta > expected_delta * 2:
                gaps.append(i)
            elif expected_delta is None and hasattr(delta, "days") and delta.days > 7:
                gaps.append(i)
        if gaps:
            report.add(QCFlag(
                "temporal_gaps", "warning",
                f"{len(gaps)} gap(s) detected in time series",
                len(gaps), len(gaps) / max(len(ts) - 1, 1),
            ))
        else:
            report.add(QCFlag("temporal_ok", "info", "No large gaps detected", 0, 0.0))
    except Exception as exc:
        report.add(QCFlag("temporal_check_failed", "warning", str(exc), 0, 0.0))
    return report
