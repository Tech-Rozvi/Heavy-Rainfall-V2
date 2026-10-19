"""
site_report.py — Executive HTML/PDF-style site report (JBA/Fathom-inspired layout).

Physical hazard only: depths, multi-peril flags, climate deltas, building counts.
No financial loss figures.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from src.utils import get_logger

logger = get_logger(__name__)

REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Site Flood Hazard Report — {{ site_name }}</title>
<style>
  body { font-family: system-ui, Segoe UI, sans-serif; margin: 2rem; color: #122; max-width: 900px; }
  h1 { border-bottom: 3px solid #1a56a0; padding-bottom: 0.4rem; }
  h2 { color: #1a56a0; margin-top: 1.75rem; }
  table { border-collapse: collapse; width: 100%; margin: 0.75rem 0 1.25rem; }
  th, td { border: 1px solid #ccd; padding: 0.45rem 0.6rem; text-align: left; }
  th { background: #e8f0fa; }
  .meta { color: #456; font-size: 0.9rem; }
  .pill { display: inline-block; padding: 0.2rem 0.55rem; border-radius: 999px; font-size: 0.8rem; margin-right: 0.35rem; }
  .high { background: #fde8e8; color: #8b1a1a; }
  .med { background: #fff3cd; color: #7a5b00; }
  .low { background: #e6f5ec; color: #1b5e3a; }
  .note { background: #f5f7fa; border-left: 4px solid #1a56a0; padding: 0.75rem 1rem; margin: 1rem 0; }
  footer { margin-top: 2rem; font-size: 0.8rem; color: #678; }
</style>
</head>
<body>
  <h1>Site Flood Hazard Report</h1>
  <p class="meta">
    <strong>{{ site_name }}</strong><br/>
    Generated: {{ generated_at }} UTC<br/>
    AOI bounds: {{ bounds_str }}<br/>
    Mode: {{ mode }}
  </p>

  <div class="note">
    Physical hazard assessment only. Depths in metres. Building counts are structure
    footprints intersecting inundation — not insured loss or monetary damage.
  </div>

  <h2>1. Multi-peril indicators</h2>
  <p>
    <span class="pill {{ peril.pluvial_class }}">Pluvial: {{ peril.pluvial }}</span>
    <span class="pill {{ peril.fluvial_class }}">Fluvial: {{ peril.fluvial }}</span>
    <span class="pill {{ peril.coastal_class }}">Coastal: {{ peril.coastal }}</span>
  </p>
  <p class="meta">{{ peril.notes }}</p>

  <h2>2. Peak water depth by return period</h2>
  <table>
    <thead><tr><th>Return period T (years)</th><th>Peak depth h<sub>max</sub> (m)</th><th>Mean depth where wet (m)</th></tr></thead>
    <tbody>
    {% for row in depth_rows %}
      <tr><td>{{ row.T }}</td><td>{{ row.h_max }}</td><td>{{ row.h_mean_wet }}</td></tr>
    {% endfor %}
    </tbody>
  </table>

  <h2>3. CMIP6 climate shift (rainfall scale factors)</h2>
  <p class="meta">Delta-change multipliers on baseline design rainfall (1 + ΔP/P<sub>hist</sub>). Replace placeholder tables with regional ensemble files for formal studies.</p>
  <table>
    <thead>
      <tr><th>SSP</th><th>2030</th><th>2050</th><th>2080</th></tr>
    </thead>
    <tbody>
    {% for row in climate_rows %}
      <tr><td>{{ row.ssp }}</td><td>{{ row.y2030 }}</td><td>{{ row.y2050 }}</td><td>{{ row.y2080 }}</td></tr>
    {% endfor %}
    </tbody>
  </table>

  <h2>4. Building exposure (physical counts)</h2>
  <p>Total footprints in AOI: <strong>{{ exposure.n_buildings }}</strong></p>
  <table>
    <thead><tr><th>Depth threshold</th><th>Structures intersecting inundation</th></tr></thead>
    <tbody>
    {% for row in exposure_rows %}
      <tr><td>{{ row.threshold }}</td><td>{{ row.count }}</td></tr>
    {% endfor %}
    </tbody>
  </table>

  <h2>5. Data sources</h2>
  <pre style="white-space:pre-wrap;font-size:0.8rem;background:#f8fafc;padding:0.75rem;">{{ sources_json }}</pre>

  <footer>
    Heavy Rainfall Model v6 — executive site report. Not a substitute for detailed engineering survey or licensed catastrophe model output.
  </footer>
</body>
</html>
"""


@dataclass
class SiteReportInput:
    site_name: str = "AOI"
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    mode: str = "api"
    depth_by_T: dict[int, Any] = field(default_factory=dict)  # T -> 2D array or scalar h_max
    exposure: Optional[dict[str, Any]] = None
    climate_scales: Optional[dict[str, dict[int, float]]] = None  # ssp -> year -> scale
    peril_flags: Optional[dict[str, str]] = None
    sources: Optional[dict[str, Any]] = None


def _severity(level: str) -> str:
    level = (level or "low").lower()
    if level in ("high", "severe"):
        return "high"
    if level in ("medium", "moderate", "med"):
        return "med"
    return "low"


def _render_jinja(template: str, ctx: dict) -> str:
    try:
        from jinja2 import Template
        return Template(template).render(**ctx)
    except ImportError:
        # Minimal fallback without jinja2
        html = template
        for k, v in ctx.items():
            if isinstance(v, str):
                html = html.replace("{{ " + k + " }}", v)
        return html


def generate_site_report(
    inp: SiteReportInput,
    output_dir: str | Path = "outputs/reports",
    *,
    write_html: bool = True,
    write_json: bool = True,
    write_docx: bool = True,
) -> dict[str, Any]:
    """
    Build executive site report (HTML + JSON sidecar).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    depth_rows = []
    for T in sorted(inp.depth_by_T.keys()):
        arr = inp.depth_by_T[T]
        import numpy as np
        if np.isscalar(arr):
            hmax = float(arr)
            hmean = float(arr)
        else:
            a = np.asarray(arr, dtype="float64")
            finite = a[np.isfinite(a)]
            hmax = float(np.nanmax(finite)) if finite.size else 0.0
            wet = finite[finite > 0.05]
            hmean = float(np.nanmean(wet)) if wet.size else 0.0
        depth_rows.append({
            "T": T,
            "h_max": f"{hmax:.3f}",
            "h_mean_wet": f"{hmean:.3f}",
        })

    # Default climate table from placeholder regional factors if none provided
    if not inp.climate_scales:
        try:
            from src.climate.cmip6_projection import _DEFAULT_DELTA_PCT
            climate_scales = {}
            for ssp in ("ssp126", "ssp245", "ssp585"):
                climate_scales[ssp] = {}
                for year in (2030, 2050, 2080):
                    pct = _DEFAULT_DELTA_PCT.get((ssp, year), 10.0)
                    climate_scales[ssp][year] = 1.0 + pct / 100.0
        except Exception:
            climate_scales = {
                "ssp245": {2030: 1.05, 2050: 1.09, 2080: 1.14},
            }
    else:
        climate_scales = inp.climate_scales

    climate_rows = []
    for ssp, years in climate_scales.items():
        climate_rows.append({
            "ssp": ssp,
            "y2030": f"{years.get(2030, float('nan')):.3f}",
            "y2050": f"{years.get(2050, float('nan')):.3f}",
            "y2080": f"{years.get(2080, float('nan')):.3f}",
        })

    exp = inp.exposure or {"n_buildings": 0, "by_threshold": {}}
    exposure_rows = []
    by = exp.get("by_threshold") or {}
    for k, v in sorted(by.items()):
        exposure_rows.append({"threshold": k, "count": v})
    if not exposure_rows:
        for t in (0.15, 0.5, 1.0):
            exposure_rows.append({"threshold": f"gt_{t}m", "count": 0})

    peril_in = inp.peril_flags or {
        "pluvial": "medium",
        "fluvial": "low",
        "coastal": "low",
        "notes": "Indicators inferred from run configuration (rainfall-driven pluvial default).",
    }
    peril = {
        "pluvial": peril_in.get("pluvial", "low"),
        "fluvial": peril_in.get("fluvial", "low"),
        "coastal": peril_in.get("coastal", "low"),
        "pluvial_class": _severity(peril_in.get("pluvial")),
        "fluvial_class": _severity(peril_in.get("fluvial")),
        "coastal_class": _severity(peril_in.get("coastal")),
        "notes": peril_in.get("notes", ""),
    }

    b = inp.bounds
    bounds_str = f"({b[0]:.4f}, {b[1]:.4f}) – ({b[2]:.4f}, {b[3]:.4f})"
    ctx = {
        "site_name": inp.site_name,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "bounds_str": bounds_str,
        "mode": inp.mode,
        "peril": peril,
        "depth_rows": depth_rows,
        "climate_rows": climate_rows,
        "exposure": exp,
        "exposure_rows": exposure_rows,
        "sources_json": json.dumps(inp.sources or {}, indent=2, default=str),
    }

    html = _render_jinja(REPORT_TEMPLATE, ctx)
    # Jinja loops need real jinja - if fallback failed, rebuild simply
    if "{%" in html:
        try:
            from jinja2 import Template
            html = Template(REPORT_TEMPLATE).render(**ctx)
        except Exception as e:
            logger.warning("Jinja2 render issue: %s", e)

    paths = {}
    if write_html:
        hp = output_dir / "site_hazard_report.html"
        hp.write_text(html, encoding="utf-8")
        paths["html"] = str(hp)
        logger.info("Wrote %s", hp)
    payload = {
        "site_name": inp.site_name,
        "bounds": list(inp.bounds),
        "mode": inp.mode,
        "depth_rows": depth_rows,
        "climate_rows": climate_rows,
        "exposure": exp,
        "peril": peril_in,
        "sources": inp.sources,
        "generated_at": ctx["generated_at"],
    }
    if write_json:
        jp = output_dir / "site_hazard_report.json"
        jp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        paths["json"] = str(jp)

    if write_docx:
        try:
            from src.reporting.docx_report import write_site_hazard_docx
            dp = write_site_hazard_docx(
                site_name=inp.site_name,
                bounds=tuple(inp.bounds),
                mode=str(inp.mode),
                depth_rows=depth_rows,
                climate_rows=climate_rows,
                exposure=exp,
                exposure_rows=exposure_rows,
                peril=peril,
                sources=inp.sources,
                generated_at=ctx["generated_at"],
                output_path=output_dir / "site_hazard_report.docx",
            )
            paths["docx"] = str(dp)
        except Exception as exc:
            logger.warning("Word report skipped: %s", exc)
            paths["docx_error"] = str(exc)

    return {"paths": paths, "html_length": len(html), "summary": payload}


def build_site_report_html(
    inp: SiteReportInput | None = None,
    output_dir: str | Path = "outputs/reports",
    **kwargs,
) -> dict:
    """
    Compatibility alias used by src.reporting.__init__ and older call sites.

    Prefer generate_site_report() in new code.
    """
    if inp is None:
        inp = SiteReportInput()
    return generate_site_report(inp, output_dir=output_dir, **kwargs)

