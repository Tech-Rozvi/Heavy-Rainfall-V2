"""
Rainfall Model — Remote Data API + Web UI

Start:
    uvicorn api.app:app --host 0.0.0.0 --port 8000

Open browser: http://127.0.0.1:8000/
"""
from __future__ import annotations

import json
import tempfile
import traceback
from pathlib import Path
from typing import Any, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

app = FastAPI(
    title="ROZVI API",
    description=(
        "ROZVI climate / extreme precipitation / flood-forcing API. "
        "Rainfall products are not flood depths. See /v1/rozvi/info."
    ),
    version="0.10.0",
)

# Phase 9 scientific routes (optional if FastAPI stack incomplete)
try:
    try:
        from api.rozvi_routes import router as rozvi_router
    except ImportError:
        from rozvi_routes import router as rozvi_router  # type: ignore
    app.include_router(rozvi_router)
except Exception as _rozvi_route_err:  # pragma: no cover
    import logging
    logging.getLogger(__name__).warning("ROZVI routes not mounted: %s", _rozvi_route_err)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def ui_home():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return {"message": "UI missing; use /docs"}
    return FileResponse(index)


@app.get("/health")
def health():
    try:
        from src.rozvi import __version__, __platform_name__, __eprf_version__
        return {
            "status": "ok",
            "service": __platform_name__,
            "version": __version__,
            "eprf_version": __eprf_version__,
        }
    except Exception:
        return {"status": "ok", "service": "ROZVI", "version": "0.8.0"}


class BBox(BaseModel):
    minx: float
    miny: float
    maxx: float
    maxy: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.minx, self.miny, self.maxx, self.maxy)


class Period(BaseModel):
    start_date: str = Field(..., examples=["2015-01-01"])
    end_date: str = Field(..., examples=["2020-12-31"])


class DataRequestBody(BaseModel):
    bbox: BBox
    period: Period
    target_resolution_m: float = 5000.0


class ModelRunBody(DataRequestBody):
    config_path: str = "config/config.yaml"
    write_outputs: bool = True


class UiRunBody(BaseModel):
    mode: str = "api"
    country: Optional[str] = "Zimbabwe"
    adm1: Optional[str] = Field(None, description="One province or comma-separated list e.g. Harare,Manicaland")
    adm2: Optional[str] = None
    adm3: Optional[str] = None
    start_date: str = "2019-01-01"
    end_date: str = "2019-12-31"
    forecast_days: int = 5
    aoi_geojson: Optional[dict[str, Any]] = None
    config_path: str = "config/default_config.yaml"


def _client():
    from src.data.streaming.remote_client import RemoteDataClient, StreamConfig
    return RemoteDataClient(StreamConfig(allow_ephemeral_temp=True))


def _arr_summary(arr: np.ndarray) -> dict:
    finite = arr[np.isfinite(arr)]
    return {
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
        "min": float(finite.min()) if finite.size else None,
        "max": float(finite.max()) if finite.size else None,
        "mean": float(finite.mean()) if finite.size else None,
        "missing_frac": float(1.0 - finite.size / max(arr.size, 1)),
    }


@app.post("/v1/data/chirps")
def data_chirps(body: DataRequestBody):
    try:
        client = _client()
        out = client.fetch_chirps_daily(body.bbox.as_tuple(), body.period.start_date, body.period.end_date)
        precip = np.asarray(out["precipitation"])
        return {"summary": _arr_summary(precip), "source": out.get("source"), "n_times": int(precip.shape[0]) if precip.ndim == 3 else 1}
    except Exception as exc:
        raise HTTPException(500, detail=str(exc)) from exc


@app.post("/v1/data/dem")
def data_dem(body: DataRequestBody):
    try:
        client = _client()
        out = client.fetch_dem(body.bbox.as_tuple())
        dem = np.asarray(out["elevation"])
        return {"summary": _arr_summary(dem), "source": out.get("source")}
    except Exception as e:
        raise HTTPException(500, detail=str(e)) from e


@app.post("/v1/ui/run")
def ui_run(body: UiRunBody):
    """
    Browser UI entrypoint — mirrors CLI main.run() for api / forecast / local.
    """
    try:
        from src.utils import load_config
        from main import run as main_run

        config_path = body.config_path
        if not Path(config_path).exists():
            alt = "config/config.yaml"
            config_path = alt if Path(alt).exists() else config_path

        aoi_path = None
        tmp = None
        if body.aoi_geojson:
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".geojson", delete=False)
            geom = body.aoi_geojson
            if geom.get("type") == "Polygon":
                fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": geom}]}
            elif geom.get("type") == "Feature":
                fc = {"type": "FeatureCollection", "features": [geom]}
            else:
                fc = geom
            json.dump(fc, tmp)
            tmp.close()
            aoi_path = tmp.name

        result = main_run(
            config_path,
            mode=body.mode,
            aoi=aoi_path,
            country=body.country,
            adm1=body.adm1,
            adm2=body.adm2,
            adm3=body.adm3,
            start_date=body.start_date,
            end_date=body.end_date,
            forecast_days=body.forecast_days,
        )
        # numpy-safe JSON
        def _clean(o):
            if isinstance(o, np.ndarray):
                return {"shape": list(o.shape), "min": float(np.nanmin(o)) if o.size else None, "max": float(np.nanmax(o)) if o.size else None, "mean": float(np.nanmean(o)) if o.size else None}
            if isinstance(o, dict):
                return {k: _clean(v) for k, v in o.items() if k != "susceptibility"}
            if isinstance(o, (list, tuple)):
                return [_clean(x) for x in o]
            if isinstance(o, (np.floating, np.integer)):
                return float(o)
            return o

        return {"ok": True, "result": _clean(result)}
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail={"error": str(exc), "trace": traceback.format_exc()[-2000:]}) from exc


@app.post("/v1/model/run")
def model_run(body: ModelRunBody):
    """Programmatic bbox + period run (API clients)."""
    try:
        from src.utils import load_config
        from src.data.manager import DataAcquisitionManager
        from main import run_pipeline

        cfg_path = body.config_path if Path(body.config_path).exists() else "config/default_config.yaml"
        if not Path(cfg_path).exists():
            cfg_path = "config/config.yaml"
        cfg = load_config(cfg_path)
        mgr = DataAcquisitionManager(cfg)
        data = mgr.acquire(
            mode="api",
            aoi_bounds=body.bbox.as_tuple(),
            start_date=body.period.start_date,
            end_date=body.period.end_date,
        )
        result = run_pipeline(cfg, data, {"source": "api_bbox"})
        return {
            "ok": True,
            "outputs": result.get("outputs"),
            "provenance": result.get("provenance"),
            "susceptibility_summary": _arr_summary(result["susceptibility"]) if "susceptibility" in result else None,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=str(e)) from e

@app.get("/v1/ui/latest-report")
def latest_report():
    """Return paths to newest site report under outputs/reports if present."""
    roots = [Path("outputs/reports"), Path("outputs/rasters/forecast/reports")]
    htmls = []
    for root in roots:
        if root.exists():
            htmls.extend(root.rglob("site_hazard_report.html"))
    if not htmls:
        return {"ok": False, "message": "No report found. Run a model job first."}
    latest = max(htmls, key=lambda p: p.stat().st_mtime)
    return {"ok": True, "html": str(latest), "json": str(latest.with_suffix(".json"))}
