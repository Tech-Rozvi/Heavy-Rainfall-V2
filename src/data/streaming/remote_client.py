"""
remote_client.py — Stream real climate/terrain data for an AOI + period.

Design rules
------------
1. Never generate synthetic observations.
2. Prefer cloud-native / windowed / subsetted remote reads.
3. Optional ephemeral temp only (auto-cleaned); no permanent data lakes.
4. ERA5 atmospheric fields come from the public AWS Open Data Zarr store
   (no CDS API key required).
"""
from __future__ import annotations

import gzip
import io
import math
import os
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)


@dataclass
class StreamConfig:
    """Controls remote access behaviour."""

    allow_ephemeral_temp: bool = True
    ephemeral_cache_dir: Optional[str] = None
    ephemeral_ttl_hours: int = 24
    request_timeout_s: int = 120
    max_retries: int = 3
    # Atmospheric source (config may override)
    era5_endpoint: str = "s3://era5-pds/zarr/"
    era5_requires_auth: bool = False


class RemoteDataClient:
    """
    High-level client used by DataAcquisitionManager and the HTTP API.

    Public methods used by the manager:
      - fetch_chirps_daily(bounds, start_date, end_date)
      - fetch_era5_land_climatology(bounds, start_date, end_date)  # AWS Zarr
      - fetch_dem(bounds)
      - fetch_distance_to_coast(bounds, resolution_m)
    """

    def __init__(self, config: Optional[StreamConfig] = None, **kwargs):
        """
        Accept StreamConfig or optional keyword overrides.
        Compatible with: RemoteDataClient(), RemoteDataClient(StreamConfig()),
        and RemoteDataClient(config=...).
        """
        if config is None and kwargs:
            config = StreamConfig(**{
                k: v for k, v in kwargs.items() if k in StreamConfig.__dataclass_fields__
            })
        self.config = config or StreamConfig()

    # ------------------------------------------------------------------
    # CHIRPS daily precipitation
    # ------------------------------------------------------------------
    def fetch_chirps_daily(
        self,
        bounds: tuple[float, float, float, float],
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """
        Daily CHIRPS rainfall for AOI bbox.

        Long periods are fetched in calendar-year chunks (ClimateSERV rejects
        multi-decade jobs with progress [-1]). Results are concatenated in time.

        Returns dict with:
          precipitation : np.ndarray (time, y, x) or (time, 1, 1) for AOI mean
          dates, units, source, transform, crs
        """
        from datetime import datetime, timedelta

        d0 = datetime.strptime(start_date, "%Y-%m-%d").date()
        d1 = datetime.strptime(end_date, "%Y-%m-%d").date()
        if d1 < d0:
            raise ValueError(f"end_date {end_date} before start_date {start_date}")

        # Single short request: try as-is first
        n_days = (d1 - d0).days + 1
        if n_days <= 400:
            try:
                return self._chirps_climateserv(bounds, start_date, end_date)
            except Exception as exc:
                logger.warning("ClimateSERV path failed (%s); trying GeoTIFF stream", exc)
                return self._chirps_geotiff_stream(bounds, start_date, end_date)

        # Long range: year-by-year ClimateSERV, with per-year GeoTIFF fallback
        chunks: list[dict] = []
        y = d0.year
        while y <= d1.year:
            c0 = max(d0, datetime(y, 1, 1).date())
            c1 = min(d1, datetime(y, 12, 31).date())
            s0, s1 = c0.isoformat(), c1.isoformat()
            logger.info("CHIRPS chunk %s → %s", s0, s1)
            try:
                chunks.append(self._chirps_climateserv(bounds, s0, s1))
            except Exception as exc:
                logger.warning(
                    "ClimateSERV chunk %s–%s failed (%s); trying GeoTIFF for that year",
                    s0, s1, exc,
                )
                try:
                    chunks.append(self._chirps_geotiff_stream(bounds, s0, s1))
                except Exception as exc2:
                    logger.error("CHIRPS chunk %s–%s failed entirely: %s", s0, s1, exc2)
            y += 1

        if not chunks:
            raise RuntimeError(
                f"No CHIRPS data retrieved for {start_date}–{end_date}. "
                "Try a shorter period or check network access to ClimateSERV / UCSB."
            )

        precip_list = []
        dates: list[str] = []
        source = chunks[0].get("source")
        transform = chunks[0].get("transform")
        crs = chunks[0].get("crs", "EPSG:4326")
        for ch in chunks:
            arr = np.asarray(ch["precipitation"])
            if arr.ndim == 1:
                arr = arr.reshape(-1, 1, 1)
            precip_list.append(arr)
            dates.extend(list(ch.get("dates") or []))

        # Align spatial shape (take min y/x)
        h = min(a.shape[1] for a in precip_list)
        w = min(a.shape[2] for a in precip_list)
        stack = np.concatenate([a[:, :h, :w] for a in precip_list], axis=0).astype("float64")

        return {
            "precipitation": stack,
            "dates": dates if dates else None,
            "units": "mm/day",
            "source": {
                "provider": "CHIRPS",
                "access": "ClimateSERV_chunked_yearly",
                "fallback": "UCSB_GeoTIFF_per_year",
                "doi": "10.1038/sdata.2015.66",
                "detail": source,
                "n_chunks": len(chunks),
            },
            "transform": transform,
            "crs": crs,
        }

    # Alias used by some call sites
    def fetch_precipitation(self, bounds, start_date, end_date):
        return self.fetch_chirps_daily(bounds, start_date, end_date)

    def _chirps_climateserv(
        self,
        bounds: tuple[float, float, float, float],
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        import json
        import requests

        minx, miny, maxx, maxy = bounds
        geom = {
            "type": "Polygon",
            "coordinates": [[
                [minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny],
            ]],
        }

        def _fmt(d: str) -> str:
            y, m, day = d.split("-")
            return f"{m}/{day}/{y}"

        base = "https://climateserv.servirglobal.net/chirps"
        params = {
            "datatype": 0,
            "begintime": _fmt(start_date),
            "endtime": _fmt(end_date),
            "intervaltype": 0,
            "operationtype": 5,
            "dateType_Category": "default",
            "isZip_CurrentDataType": "false",
            "geometry": json.dumps(geom),
        }
        r = requests.get(
            f"{base}/submitDataRequest/",
            params=params,
            timeout=self.config.request_timeout_s,
        )
        r.raise_for_status()
        job = r.json()
        if isinstance(job, list):
            job_id = job[0]
        elif isinstance(job, dict):
            job_id = job.get("id") or job.get("job_id") or next(iter(job.values()))
        else:
            job_id = job

        for _ in range(90):
            prog = requests.get(
                f"{base}/getDataRequestProgress/",
                params={"id": job_id},
                timeout=30,
            )
            prog.raise_for_status()
            val = prog.json()
            pct = val[0] if isinstance(val, list) else val
            if pct is None:
                time.sleep(2)
                continue
            if float(pct) >= 100:
                break
            if float(pct) < 0:
                raise RuntimeError(f"ClimateSERV job failed: {val}")
            time.sleep(2)
        else:
            raise TimeoutError("ClimateSERV job timed out")

        data_resp = requests.get(
            f"{base}/getDataFromRequest/",
            params={"id": job_id},
            timeout=60,
        )
        data_resp.raise_for_status()
        payload = data_resp.json()

        dates, values = [], []
        records = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(records, list):
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                d = rec.get("isodate") or rec.get("date") or rec.get("Date")
                v = rec.get("raw_value", None)
                if v is None:
                    v = rec.get("value")
                # ClimateSERV often returns value as {"avg": float, ...}
                if isinstance(v, dict):
                    v = v.get("avg", v.get("max", v.get("min")))
                if v is None:
                    v = rec.get("avg")
                if d is not None and v is not None:
                    dates.append(str(d))
                    try:
                        values.append(float(v))
                    except (TypeError, ValueError):
                        values.append(np.nan)
        if not values:
            raise RuntimeError(f"ClimateSERV returned no values: {str(payload)[:400]}")

        arr = np.asarray(values, dtype="float64").reshape(-1, 1, 1)
        return {
            "precipitation": arr,
            "dates": dates,
            "units": "mm/day",
            "source": {
                "provider": "CHIRPS",
                "access": "ClimateSERV_API",
                "url": base,
                "doi": "10.1038/sdata.2015.66",
            },
            "transform": None,
            "crs": "EPSG:4326",
        }

    def _chirps_geotiff_stream(
        self,
        bounds: tuple[float, float, float, float],
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        import requests
        from rasterio.io import MemoryFile
        from rasterio.windows import from_bounds

        d0 = datetime.strptime(start_date, "%Y-%m-%d")
        d1 = datetime.strptime(end_date, "%Y-%m-%d")
        n_days = (d1 - d0).days + 1
        if n_days > 400:
            raise ValueError(
                f"Date range too long for single GeoTIFF stream ({n_days} days). "
                "fetch_chirps_daily() chunks by year automatically; "
                "call that instead of _chirps_geotiff_stream for long periods."
            )

        base = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05"
        minx, miny, maxx, maxy = bounds
        buffer = 0.1
        win_bounds = (minx - buffer, miny - buffer, maxx + buffer, maxy + buffer)

        arrays, dates = [], []
        transform = None
        cur = d0
        while cur <= d1:
            url = (
                f"{base}/{cur.year}/"
                f"chirps-v2.0.{cur.year}.{cur.month:02d}.{cur.day:02d}.tif.gz"
            )
            try:
                resp = requests.get(url, timeout=self.config.request_timeout_s)
                if resp.status_code == 404:
                    cur += timedelta(days=1)
                    continue
                resp.raise_for_status()
                raw = gzip.decompress(resp.content)
                with MemoryFile(raw) as mem:
                    with mem.open() as src:
                        window = from_bounds(*win_bounds, transform=src.transform)
                        data = src.read(1, window=window).astype("float32")
                        data = np.where(data < -9000, np.nan, data)
                        if transform is None:
                            transform = src.window_transform(window)
                        arrays.append(data)
                        dates.append(cur.strftime("%Y-%m-%d"))
            except Exception as exc:
                logger.warning("CHIRPS stream miss %s: %s", cur.date(), exc)
            cur += timedelta(days=1)

        if not arrays:
            raise RuntimeError("No CHIRPS data streamed for AOI/period.")

        h = min(a.shape[0] for a in arrays)
        w = min(a.shape[1] for a in arrays)
        stack = np.stack([a[:h, :w] for a in arrays], axis=0).astype("float64")
        return {
            "precipitation": stack,
            "dates": dates,
            "units": "mm/day",
            "source": {
                "provider": "CHIRPS",
                "access": "HTTP_GeoTIFF_windowed_stream",
                "url": base,
                "doi": "10.1038/sdata.2015.66",
            },
            "transform": transform,
            "crs": "EPSG:4326",
        }

    # ------------------------------------------------------------------
    # ERA5 atmospheric — public AWS Open Data Zarr (no CDS key)
    # ------------------------------------------------------------------


    def fetch_precip_open_meteo(
        self,
        bounds: tuple[float, float, float, float],
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """Daily precipitation [mm] at AOI centroid via Open-Meteo Archive (real data)."""
        import requests
        from datetime import datetime, timedelta

        minx, miny, maxx, maxy = bounds
        lat = (miny + maxy) / 2.0
        lon = (minx + maxx) / 2.0
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "daily": "precipitation_sum",
            "timezone": "UTC",
        }
        last_err = None
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, timeout=self.config.request_timeout_s)
                r.raise_for_status()
                daily = (r.json().get("daily") or {})
                vals = daily.get("precipitation_sum") or []
                dates = daily.get("time") or []
                if not vals:
                    raise RuntimeError("empty precipitation_sum")
                arr = np.asarray(vals, dtype="float64").reshape(-1, 1, 1)
                arr = np.nan_to_num(arr, nan=0.0)
                arr = np.maximum(arr, 0.0)
                return {
                    "precipitation": arr,
                    "dates": list(dates),
                    "units": "mm/day",
                    "source": {
                        "provider": "OpenMeteo_Archive",
                        "access": "HTTP_API",
                        "url": url,
                        "point": {"lat": lat, "lon": lon},
                    },
                    "transform": None,
                    "crs": "EPSG:4326",
                }
            except Exception as exc:
                last_err = exc
        raise RuntimeError(f"Open-Meteo precip failed: {last_err}")



    def fetch_land_cover(self, bounds, resolution_m: float = 100.0):
        from src.data.streaming.surface_layers import fetch_land_cover as _flc
        return _flc(bounds, resolution_m=resolution_m, timeout_s=self.config.request_timeout_s)

    def fetch_soil_texture(self, bounds, resolution_m: float = 250.0):
        from src.data.streaming.surface_layers import fetch_soil_hsg
        return fetch_soil_hsg(bounds, resolution_m=resolution_m)

    def fetch_forecast_precip(self, bounds, forecast_days: int = 5):
        from src.data.streaming.surface_layers import fetch_forecast_qpf
        return fetch_forecast_qpf(bounds, forecast_days=forecast_days, timeout_s=self.config.request_timeout_s)

    def fetch_era5_land_climatology(
        self,
        bounds: tuple[float, float, float, float],
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """
        Period-mean 2 m temperature (°C), RH (%), 10 m wind (m/s).

        Tries public ARCO ERA5 Zarr first; on failure uses Open-Meteo
        Archive API (real observations/reanalysis blend, no API key).
        Never invents synthetic atmosphere.
        """
        try:
            return self._era5_arco_zarr(bounds, start_date, end_date)
        except Exception as exc:
            logger.warning("ARCO ERA5 failed (%s); trying Open-Meteo archive", exc)
            return self._era5_open_meteo(bounds, start_date, end_date)

    def fetch_era5_aws_zarr(self, bounds, start_date, end_date):
        return self.fetch_era5_land_climatology(bounds, start_date, end_date)

    def _era5_arco_zarr(
        self,
        bounds: tuple[float, float, float, float],
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        import fsspec
        import xarray as xr

        minx, miny, maxx, maxy = bounds
        candidates = [
            "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3",
            "https://storage.googleapis.com/gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3",
            "gs://gcp-public-data-arco-era5/ar/1959-2022-full_37-1h-0p25deg-chunk-1.zarr-v3",
            self.config.era5_endpoint.rstrip("/") + "/",
        ]
        last_err: Optional[Exception] = None
        ds = None
        used_url = None

        for url in candidates:
            try:
                logger.info("Opening ERA5 Zarr: %s", url)
                if url.startswith("gs://"):
                    mapper = fsspec.get_mapper(url, token="anon")
                    ds = xr.open_zarr(mapper, consolidated=True)
                elif url.startswith("s3://"):
                    mapper = fsspec.get_mapper(
                        url,
                        anon=True,
                        client_kwargs={"region_name": "us-east-1"},
                    )
                    ds = xr.open_zarr(mapper, consolidated=True)
                else:
                    mapper = fsspec.get_mapper(url)
                    try:
                        ds = xr.open_zarr(mapper, consolidated=True)
                    except Exception:
                        ds = xr.open_zarr(mapper, consolidated=False)
                # Validate coords exist
                coords = list(ds.coords) + list(ds.dims)
                if not coords:
                    raise RuntimeError("opened empty dataset")
                used_url = url
                break
            except Exception as exc:
                last_err = exc
                logger.warning("ERA5 open failed for %s: %s", url, exc)
                ds = None

        if ds is None:
            raise RuntimeError(f"Could not open ARCO ERA5 Zarr: {last_err}")

        # Discover lat/lon coordinate names (incl. dims-only)
        names = set(map(str, list(ds.coords) + list(ds.dims) + list(ds.variables)))
        lat_name = next((n for n in ("latitude", "lat", "Latitude") if n in names), None)
        lon_name = next((n for n in ("longitude", "lon", "Longitude") if n in names), None)
        if lat_name is None or lon_name is None:
            raise RuntimeError(f"ERA5 store missing lat/lon coords: {list(ds.coords)} dims={list(ds.dims)}")

        lon_vals = np.asarray(ds[lon_name].values)
        use_0_360 = float(np.nanmax(lon_vals)) > 180.5
        lon_min, lon_max = (minx % 360, maxx % 360) if use_0_360 else (minx, maxx)
        lat = ds[lat_name]
        lat_ascending = bool(np.asarray(lat.values).ravel()[0] < np.asarray(lat.values).ravel()[-1])
        lat_slice = slice(miny, maxy) if lat_ascending else slice(maxy, miny)

        def _find_var(*cands):
            lower = {str(k).lower(): k for k in ds.data_vars}
            for n in cands:
                if n in ds.data_vars:
                    return n
                if n.lower() in lower:
                    return lower[n.lower()]
            return None

        t_name = _find_var("2m_temperature", "t2m", "temperature_2m", "air_temperature_at_2_metres")
        u_name = _find_var("10m_u_component_of_wind", "u10", "eastward_wind_at_10_metres")
        v_name = _find_var("10m_v_component_of_wind", "v10", "northward_wind_at_10_metres")
        d_name = _find_var("2m_dewpoint_temperature", "d2m", "dewpoint_temperature_2m")
        if t_name is None:
            raise RuntimeError(f"No 2m temperature in ERA5 vars={list(ds.data_vars)[:25]}")

        def _subset(var_name: str):
            da = ds[var_name]
            time_name = next((d for d in ("time", "valid_time") if d in da.dims), None)
            if time_name:
                da = da.sel({time_name: slice(start_date, end_date)})
            da = da.sel({lat_name: lat_slice, lon_name: slice(lon_min, lon_max)})
            return da

        t_da = _subset(t_name)
        reduce_dims = [d for d in t_da.dims if d not in (lat_name, lon_name)]
        t_vals = np.asarray(t_da.mean(dim=reduce_dims).values if reduce_dims else t_da.values, dtype="float64")
        if np.nanmean(t_vals) > 100:
            t_vals = t_vals - 273.15

        if d_name:
            d_da = _subset(d_name)
            td = np.asarray(d_da.mean(dim=reduce_dims).values if reduce_dims else d_da.values, dtype="float64")
            if np.nanmean(td) > 100:
                td = td - 273.15
            es = 6.112 * np.exp((17.67 * t_vals) / (t_vals + 243.5))
            e = 6.112 * np.exp((17.67 * td) / (td + 243.5))
            rh = np.clip(e / es * 100.0, 0.0, 100.0)
        else:
            rh = np.full_like(t_vals, np.nan)

        if u_name and v_name:
            u = np.asarray(_subset(u_name).mean(dim=reduce_dims).values if reduce_dims else _subset(u_name).values)
            v = np.asarray(_subset(v_name).mean(dim=reduce_dims).values if reduce_dims else _subset(v_name).values)
            wind = np.sqrt(u.astype("float64") ** 2 + v.astype("float64") ** 2)
        else:
            wind = np.full_like(t_vals, np.nan)

        return {
            "temperature": t_vals,
            "relative_humidity": rh,
            "wind_speed": wind,
            "units": {"temperature": "degC", "relative_humidity": "%", "wind_speed": "m/s"},
            "source": {
                "provider": "ERA5_ARCO",
                "access": "Zarr_fsspec",
                "url": used_url,
                "requires_auth": False,
            },
            "crs": "EPSG:4326",
        }

    def _era5_open_meteo(
        self,
        bounds: tuple[float, float, float, float],
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """
        Real atmospheric climatology via Open-Meteo Archive API (no key).
        Uses AOI centroid; returns 1x1 maps (aligned later by manager).
        """
        import requests

        minx, miny, maxx, maxy = bounds
        lat = (miny + maxy) / 2.0
        lon = (minx + maxx) / 2.0
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_mean,relative_humidity_2m_mean,wind_speed_10m_mean",
            "timezone": "UTC",
        }
        r = requests.get(url, params=params, timeout=self.config.request_timeout_s)
        r.raise_for_status()
        payload = r.json()
        daily = payload.get("daily") or {}
        t = np.asarray(daily.get("temperature_2m_mean") or [], dtype="float64")
        rh = np.asarray(daily.get("relative_humidity_2m_mean") or [], dtype="float64")
        w = np.asarray(daily.get("wind_speed_10m_mean") or [], dtype="float64")
        if t.size == 0:
            raise RuntimeError(f"Open-Meteo returned no daily data: {str(payload)[:300]}")
        # wind often in km/h from Open-Meteo → m/s
        if np.nanmean(w) > 20:  # likely km/h
            w = w / 3.6
        t_m = float(np.nanmean(t))
        rh_m = float(np.nanmean(rh)) if rh.size else np.nan
        w_m = float(np.nanmean(w)) if w.size else np.nan
        one = np.array([[t_m]], dtype="float64")
        return {
            "temperature": one,
            "relative_humidity": np.array([[rh_m]], dtype="float64"),
            "wind_speed": np.array([[w_m]], dtype="float64"),
            "units": {"temperature": "degC", "relative_humidity": "%", "wind_speed": "m/s"},
            "source": {
                "provider": "OpenMeteo_Archive",
                "access": "HTTP_API",
                "url": url,
                "point": {"lat": lat, "lon": lon},
                "requires_auth": False,
                "note": "AOI-centroid climatology (real archive data)",
            },
            "crs": "EPSG:4326",
        }

    # ------------------------------------------------------------------
    # Copernicus DEM — COG HTTP stream
    # ------------------------------------------------------------------
    def fetch_dem(self, bounds: tuple[float, float, float, float]) -> dict[str, Any]:
        import requests
        import rasterio
        from rasterio.io import MemoryFile
        from rasterio.merge import merge as rio_merge
        from rasterio.windows import from_bounds as window_from_bounds

        minx, miny, maxx, maxy = bounds
        tiles = []
        for lat in range(int(math.floor(miny)), int(math.ceil(maxy))):
            for lon in range(int(math.floor(minx)), int(math.ceil(maxx))):
                ns = "N" if lat >= 0 else "S"
                ew = "E" if lon >= 0 else "W"
                tile = f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"
                tiles.append(tile)

        if len(tiles) > 80:
            raise ValueError(f"AOI requires {len(tiles)} DEM tiles (limit 80). Reduce extent.")

        base = "https://copernicus-dem-30m.s3.amazonaws.com"
        datasets, memfiles = [], []
        try:
            for tile in tiles:
                url = f"{base}/{tile}/{tile}.tif"
                try:
                    resp = requests.get(url, timeout=self.config.request_timeout_s)
                    if resp.status_code == 404:
                        continue
                    resp.raise_for_status()
                    mem = MemoryFile(resp.content)
                    memfiles.append(mem)
                    datasets.append(mem.open())
                except Exception as exc:
                    logger.warning("DEM tile skip %s: %s", tile, exc)

            if not datasets:
                raise RuntimeError("No DEM tiles could be streamed for AOI.")

            mosaic, transform = rio_merge(datasets)
            elev = mosaic[0].astype("float64")
            elev = np.where(elev < -1000, np.nan, elev)
            try:
                window = window_from_bounds(minx, miny, maxx, maxy, transform=transform)
                r0, c0 = max(0, int(window.row_off)), max(0, int(window.col_off))
                h, w = int(window.height), int(window.width)
                elev = elev[r0:r0 + h, c0:c0 + w]
                transform = rasterio.windows.transform(
                    rasterio.windows.Window(c0, r0, elev.shape[1], elev.shape[0]),
                    transform,
                )
            except Exception:
                pass
        finally:
            for ds in datasets:
                ds.close()
            for m in memfiles:
                m.close()

        return {
            "elevation": elev,
            "transform": transform,
            "crs": "EPSG:4326",
            "units": "m",
            "source": {
                "provider": "Copernicus_DEM_GLO30",
                "access": "AWS_COG_HTTP_stream",
                "url": base,
            },
        }

    # ------------------------------------------------------------------
    # Natural Earth coastline distance
    # ------------------------------------------------------------------
    def fetch_distance_to_coast(
        self,
        bounds: tuple[float, float, float, float],
        resolution_m: float = 5000.0,
    ) -> dict[str, Any]:
        import requests
        import geopandas as gpd
        from shapely.ops import unary_union
        from rasterio.transform import from_bounds

        url = "https://naciscdn.org/naturalearth/10m/physical/ne_10m_coastline.zip"
        resp = requests.get(url, timeout=self.config.request_timeout_s)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with tempfile.TemporaryDirectory() as tmp:
                zf.extractall(tmp)
                shps = list(Path(tmp).glob("**/*.shp"))
                if not shps:
                    raise RuntimeError("Natural Earth coastline shapefile missing in zip")
                coast = gpd.read_file(shps[0]).to_crs("EPSG:4326")

        minx, miny, maxx, maxy = bounds
        res_deg = resolution_m / 111_320.0
        width = max(2, int(np.ceil((maxx - minx) / res_deg)))
        height = max(2, int(np.ceil((maxy - miny) / res_deg)))
        coast_m = coast.to_crs("EPSG:3857")
        coast_geom = unary_union(coast_m.geometry.values)
        xs = np.linspace(minx + res_deg / 2, maxx - res_deg / 2, width)
        ys = np.linspace(maxy - res_deg / 2, miny + res_deg / 2, height)
        xx, yy = np.meshgrid(xs, ys)
        pts = gpd.GeoDataFrame(
            geometry=gpd.points_from_xy(xx.ravel(), yy.ravel()), crs="EPSG:4326"
        ).to_crs("EPSG:3857")
        dist_km = (pts.geometry.distance(coast_geom).values / 1000.0).reshape(height, width)
        transform = from_bounds(minx, miny, maxx, maxy, width, height)
        return {
            "distance_to_coast": dist_km.astype("float64"),
            "transform": transform,
            "crs": "EPSG:4326",
            "units": "km",
            "source": {
                "provider": "Natural_Earth_coastline",
                "access": "HTTP_stream",
                "url": url,
                "metric": "distance_to_ocean_coastline",
            },
        }
