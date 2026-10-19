"""
Heavy-Rainfall-Model v4 — CLI entrypoint.

Examples
--------
python main.py --mode api --country Zimbabwe --adm1 Harare --start-date 2019-01-01 --end-date 2019-12-31
python main.py --mode api --aoi examples/harare_qa_small.geojson --start-date 2019-01-01 --end-date 2019-12-31
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

import numpy as np

from src.utils import get_logger, load_config

logger = get_logger("main")


def _sanitize_cli_str(val: Optional[str]) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip().strip('"').strip("'")
    s = " ".join(s.split())
    return s or None


def _validate_dates(
    start: Optional[str], end: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    from datetime import datetime

    def _parse(d: Optional[str]) -> Optional[str]:
        if not d:
            return None
        d = _sanitize_cli_str(d)
        datetime.strptime(d, "%Y-%m-%d")  # type: ignore[arg-type]
        return d

    start, end = _parse(start), _parse(end)
    if start and end and start > end:
        raise ValueError(f"start-date {start} is after end-date {end}")
    return start, end


def _bounds_from_aoi(path: str) -> tuple[tuple[float, float, float, float], dict]:
    import geopandas as gpd

    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")
    minx, miny, maxx, maxy = gdf.total_bounds
    return (float(minx), float(miny), float(maxx), float(maxy)), {
        "source": f"aoi_file:{path}",
        "n_features": int(len(gdf)),
    }


def run_pipeline(cfg: dict, data: Any, meta: dict) -> dict[str, Any]:
    """
    Core rainfall-index / susceptibility path using acquired arrays.
    Lightweight production path (full AHP stack can be wired here later).
    """
    daily = np.asarray(data.daily_precip, dtype="float64")
    if daily.ndim == 3:
        with np.errstate(all="ignore"):
            map_mm = np.nanmean(daily, axis=0) * 365.25
            rx1 = np.nanmax(daily, axis=0)
            p95 = np.nanpercentile(daily, 95, axis=0)
    else:
        map_mm = daily
        rx1 = daily
        p95 = daily

    def _norm(a: np.ndarray) -> np.ndarray:
        a = np.nan_to_num(np.asarray(a, dtype="float64"), nan=0.0)
        lo, hi = np.nanmin(a), np.nanmax(a)
        if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-12:
            return np.zeros_like(a)
        return (a - lo) / (hi - lo)

    # Simple weighted susceptibility (0–1) from rain + terrain + atmosphere
    s_map = _norm(map_mm)
    s_rx = _norm(rx1)
    s_p95 = _norm(p95)
    s_slope = _norm(data.slope)
    s_asp = _norm(data.aspect_exposure)
    s_t = _norm(data.temperature)
    s_rh = _norm(data.relative_humidity)
    s_w = _norm(data.wind_speed)
    s_coast = 1.0 - _norm(data.distance_to_coast)

    susceptibility = (
        0.22 * s_map
        + 0.18 * s_rx
        + 0.15 * s_p95
        + 0.12 * s_slope
        + 0.08 * s_asp
        + 0.08 * s_t
        + 0.07 * s_rh
        + 0.05 * s_w
        + 0.05 * s_coast
    )
    susceptibility = np.clip(np.nan_to_num(susceptibility, nan=0.0), 0.0, 1.0)

    from src.rozvi.legacy import warn_legacy_susceptibility, susceptibility_product_metadata
    warn_legacy_susceptibility()
    legacy_meta = susceptibility_product_metadata(
        extra={"weights": {"map": 0.22, "rx1": 0.18, "p95": 0.15}}
    )

    out_dir = Path(cfg.get("paths", {}).get("output_dir", "outputs"))
    raster_dir = out_dir / "rasters"
    raster_dir.mkdir(parents=True, exist_ok=True)

    # GeoTIFF export when transform available
    written = []
    try:
        import rasterio
        from rasterio.transform import Affine

        transform = data.transform
        if transform is None:
            # build affine from shape
            transform = Affine.identity()
        profile = {
            "driver": "GTiff",
            "height": susceptibility.shape[0],
            "width": susceptibility.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": data.crs or "EPSG:4326",
            "transform": transform,
            "nodata": -9999.0,
            "compress": "deflate",
        }
        path = raster_dir / "susceptibility.tif"
        arr = susceptibility.astype("float32")
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr, 1)
            dst.update_tags(
                product_label="legacy_relative_susceptibility",
                validation_status="legacy_diagnostic",
                disclaimer=legacy_meta["disclaimer"][:256],
                is_flood_depth="false",
            )
        written.append(str(path))
        logger.info("Wrote %s (legacy diagnostic)", path)
    except Exception as exc:
        logger.warning("GeoTIFF export skipped: %s", exc)
        np.save(raster_dir / "susceptibility.npy", susceptibility)
        written.append(str(raster_dir / "susceptibility.npy"))

    provenance = {
        "mode": data.mode,
        "aoi": meta,
        "sources": data.sources,
        "resolution_m": data.resolution_m,
        "n_years": data.n_years,
        "outputs": written,
        "product_metadata": legacy_meta,
    }
    prov_path = out_dir / "provenance.json"
    prov_path.write_text(json.dumps(provenance, indent=2, default=str), encoding="utf-8")
    logger.info("Provenance → %s", prov_path)

    # Executive HTML report (physical hazard summary)
    try:
        from src.reporting.site_report import generate_site_report, SiteReportInput
        generate_site_report(
            SiteReportInput(
                site_name=str(meta.get("display_name") or meta.get("source") or "AOI"),
                bounds=tuple(meta.get("bounds") or (0, 0, 0, 0)) if isinstance(meta.get("bounds"), (list, tuple)) else (0, 0, 0, 0),
                mode=str(data.mode),
                depth_by_T={},  # susceptibility path: depth optional
                exposure={"n_buildings": 0, "by_threshold": {}},
                sources=data.sources,
                peril_flags={
                    "pluvial": "medium",
                    "fluvial": "low",
                    "coastal": "low",
                    "notes": "Susceptibility screening run; enable --mode forecast or hydraulics for depth maps.",
                },
            ),
            output_dir=out_dir / "reports",
        )
    except Exception as exc:
        logger.warning("Site report skipped: %s", exc)

    return {
        "susceptibility": susceptibility,
        "map_mm": map_mm,
        "provenance": provenance,
        "outputs": written,
        "product_metadata": legacy_meta,
    }


def run(
    config_path: str,
    *,
    mode: Optional[str] = None,
    aoi: Optional[str] = None,
    country: Optional[str] = None,
    adm1: Optional[str] = None,
    adm2: Optional[str] = None,
    adm3: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    allow_synthetic: bool = False,
    generate_synthetic_data: bool = False,
    forecast_days: int = 5,
    point: Optional[str] = None,
    bbox: Optional[str] = None,
    crs: Optional[str] = None,
    buffer_km: Optional[float] = None,
) -> dict[str, Any]:
    # Prefer unified ROZVI config when path points at default legacy file
    try:
        from src.rozvi.config import load_rozvi_config
        if config_path in ("config/default_config.yaml", "config/config.yaml"):
            cfg = load_rozvi_config("config/rozvi.yaml")
        else:
            cfg = load_config(config_path)
    except Exception:
        cfg = load_config(config_path)
    cfg["_forecast_days"] = int(forecast_days)
    paths = cfg.get("paths", {})
    for p in paths.values():
        Path(str(p)).mkdir(parents=True, exist_ok=True)

    country = _sanitize_cli_str(country)
    adm1 = _sanitize_cli_str(adm1)
    adm2 = _sanitize_cli_str(adm2)
    adm3 = _sanitize_cli_str(adm3)
    aoi = _sanitize_cli_str(aoi)
    point = _sanitize_cli_str(point)
    bbox = _sanitize_cli_str(bbox)
    crs = _sanitize_cli_str(crs)
    start_date, end_date = _validate_dates(start_date, end_date)

    mode = (mode or cfg.get("data_acquisition", {}).get("mode", "api")).lower()
    sci = cfg.get("scientific_options", {})
    allow_synth = bool(
        allow_synthetic
        or generate_synthetic_data
        or sci.get("allow_synthetic_data", False)
    )
    if generate_synthetic_data and not allow_synth:
        raise RuntimeError(
            "Refusing synthetic data. Pass --allow-synthetic with --generate-synthetic-data."
        )
    if allow_synth:
        logger.warning("Synthetic mode allowed by flag (not recommended for production).")

    from src.data.manager import DataAcquisitionManager, resolve_gaul_bounds

    bounds = None
    meta: dict[str, Any] = {}
    # --- Universal AOI via ROZVI / EPRF (point, bbox, or file) ---
    if point or bbox or (aoi and Path(aoi).exists()):
        try:
            from src.rozvi.orchestrator import resolve_aoi, write_run_manifest
            pt = None
            bb = None
            if point:
                parts = [float(x) for x in point.replace(",", " ").split()]
                if len(parts) != 2:
                    raise SystemExit("--point requires two numbers: x,y or lon,lat")
                pt = (parts[0], parts[1])
            if bbox:
                parts = [float(x) for x in bbox.replace(",", " ").split()]
                if len(parts) != 4:
                    raise SystemExit("--bbox requires xmin,ymin,xmax,ymax")
                bb = parts
            aoi_rec, diag = resolve_aoi(
                source=aoi if aoi and not pt and not bb else None,
                bbox=bb,
                point=pt,
                crs=crs,
                buffer_km=buffer_km,
                config=cfg,
            )
            bounds = aoi_rec.bounds
            meta = {
                "source": "rozvi_aoi",
                "aoi_id": aoi_rec.aoi_id,
                "crs_confidence": aoi_rec.crs_confidence,
                "diagnostic": diag,
            }
            out_dir = Path(cfg.get("paths", {}).get("output_dir", "outputs"))
            write_run_manifest(out_dir / "manifests", aoi=aoi_rec, diagnostic=diag, config=cfg)
            logger.info("AOI resolved id=%s bounds=%s", aoi_rec.aoi_id, bounds)
        except SystemExit:
            raise
        except Exception as exc:
            if aoi:
                logger.warning("ROZVI AOI path failed (%s); falling back to legacy bounds", exc)
                bounds, meta = _bounds_from_aoi(aoi)
            else:
                raise SystemExit(f"AOI resolution failed: {exc}")
    elif aoi:
        bounds, meta = _bounds_from_aoi(aoi)
        logger.info("AOI from file %s → %s", aoi, bounds)
    elif country or adm1:
        gaul_cfg = cfg.get("gaul", {}) or cfg.get("paths", {})
        bounds, meta = resolve_gaul_bounds(
            country=country,
            adm1=adm1,
            adm2=adm2,
            adm3=adm3,
            gaul_data_dir=gaul_cfg.get("data_dir", "data/boundaries/gaul"),
            gaul_layer=gaul_cfg.get("layer"),
        )
        logger.info("AOI from admin hierarchy %s → %s", meta, bounds)
    else:
        raise SystemExit(
            "Provide --aoi path, --point x,y, --bbox xmin,ymin,xmax,ymax, "
            "or --country/--adm1."
        )

    if not start_date or not end_date:
        raise SystemExit("Provide --start-date and --end-date as YYYY-MM-DD.")


    if mode == "forecast":
        from src.data.manager import DataAcquisitionManager
        from src.hydraulics.forecast_run import run_forecast_flood
        manager = DataAcquisitionManager(cfg)
        # Forecast mode needs DEM (+ soft atmosphere). Historical CHIRPS is skipped
        # automatically when --start-date is in the future / within latency.
        # QPF comes from Open-Meteo inside run_forecast_flood — not CHIRPS.
        data = manager.acquire(
            mode="api",
            aoi_bounds=bounds,
            start_date=start_date or "2020-01-01",
            end_date=end_date or "2020-01-05",
        )
        # forecast_days from cfg or default 5 — CLI wired in main()
        fd = int(cfg.get("_forecast_days", 5))
        result = run_forecast_flood(
            data.dem,
            bounds,
            dx=float(data.resolution_m) if data.resolution_m < 500 else 30.0,
            dy=float(data.resolution_m) if data.resolution_m < 500 else 30.0,
            transform=data.transform,
            forecast_days=fd,
            output_dir=Path(cfg.get("paths", {}).get("output_dir", "outputs")) / "rasters" / "forecast",
        )
        logger.info("Forecast mode complete: %s", result.get("report"))
        return result

    manager = DataAcquisitionManager(cfg)
    data = manager.acquire(
        mode=mode,
        aoi_bounds=bounds,
        start_date=start_date,
        end_date=end_date,
    )
    result = run_pipeline(cfg, data, meta)
    logger.info("Run complete. Outputs: %s", result.get("outputs"))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ROZVI / Heavy Rainfall Model — rainfall, extremes, and flood-forcing CLI"
    )
    parser.add_argument("--config", default="config/rozvi.yaml")
    parser.add_argument("--mode", choices=["api", "local", "auto", "forecast"], default="api")
    parser.add_argument("--forecast-days", type=int, default=5, help="QPF horizon 1-7 days for --mode forecast")
    parser.add_argument("--aoi", default=None, help="Vector AOI path (GeoJSON/GPKG/SHP/…)")
    parser.add_argument("--point", default=None, help="x,y or lon,lat (use --crs for projected)")
    parser.add_argument("--bbox", default=None, help="xmin,ymin,xmax,ymax")
    parser.add_argument("--crs", default=None, help="CRS of --point/--bbox/file if not embedded")
    parser.add_argument("--buffer-km", type=float, default=None, help="Point buffer radius km")
    parser.add_argument("--country", default=None)
    parser.add_argument("--adm1", default=None, help="Province name(s), comma-separated for multi e.g. Harare,Bulawayo")
    parser.add_argument("--adm2", default=None)
    parser.add_argument("--adm3", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--allow-synthetic", action="store_true")
    parser.add_argument("--generate-synthetic-data", action="store_true")
    args = parser.parse_args()
    run(
        args.config,
        mode=args.mode,
        aoi=args.aoi,
        country=args.country,
        adm1=args.adm1,
        adm2=args.adm2,
        adm3=args.adm3,
        start_date=args.start_date,
        end_date=args.end_date,
        point=args.point,
        bbox=args.bbox,
        crs=args.crs,
        buffer_km=args.buffer_km,
        allow_synthetic=args.allow_synthetic,
        generate_synthetic_data=args.generate_synthetic_data,
        forecast_days=getattr(args, 'forecast_days', 5),
    )


if __name__ == "__main__":
    main()
