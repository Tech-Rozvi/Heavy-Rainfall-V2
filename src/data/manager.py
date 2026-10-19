"""
manager.py — Unified data acquisition (local real files | remote API stream).

Modes
-----
api    — stream CHIRPS / DEM / ERA5 (AWS Zarr) / Natural Earth into memory
local  — load client-supplied real files under data/raw/

Synthetic data is never produced here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from src.utils import get_logger, read_geotiff
from src import terrain as terr
from src.data.streaming.remote_client import RemoteDataClient, StreamConfig

logger = get_logger(__name__)


def _dates_need_chirps(start_date: str, end_date: str) -> tuple[bool, str]:
    """CHIRPS is historical only; skip pure-future or ultra-recent windows."""
    from datetime import datetime, timezone, timedelta
    try:
        d0 = datetime.strptime(str(start_date)[:10], "%Y-%m-%d").date()
        d1 = datetime.strptime(str(end_date)[:10], "%Y-%m-%d").date()
    except Exception:
        return True, "unparseable_dates"
    today = datetime.now(timezone.utc).date()
    if d0 > today:
        return False, f"start_date {start_date} is in the future (CHIRPS is historical)"
    if d1 > today + timedelta(days=1):
        return False, f"end_date {end_date} is beyond CHIRPS availability"
    if d0 > today - timedelta(days=5):
        return False, f"start_date {start_date} within CHIRPS latency window (~5 days)"
    return True, "ok"


CHIRPS_RESOLUTION_M = 5000.0


@dataclass
class AcquisitionResult:
    daily_precip: np.ndarray
    n_years: float
    dem: np.ndarray
    slope: np.ndarray
    aspect_exposure: np.ndarray
    temperature: np.ndarray
    relative_humidity: np.ndarray
    wind_speed: np.ndarray
    distance_to_coast: np.ndarray
    transform: Any
    crs: str
    resolution_m: float
    mode: str = "api"
    sources: dict = field(default_factory=dict)
    dates: list = field(default_factory=list)


def _fill_nan_nearest(arr: np.ndarray) -> np.ndarray:
    """Fill NaN holes/margins by nearest finite neighbour (no empty borders)."""
    a = np.asarray(arr, dtype="float64")
    if np.isfinite(a).all():
        return a
    if not np.isfinite(a).any():
        return np.zeros_like(a)
    try:
        from scipy.ndimage import distance_transform_edt
        mask = ~np.isfinite(a)
        idx = distance_transform_edt(mask, return_distances=False, return_indices=True)
        return a[tuple(idx)]
    except Exception:
        fill = float(np.nanmean(a)) if np.isfinite(a).any() else 0.0
        return np.where(np.isfinite(a), a, fill)


def _fit_to_shape(arr: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Resample to target (H, W). Handles scalars, 0-D, 1-D, 1x1, and 2-D."""
    th, tw = int(shape[0]), int(shape[1])
    target = (th, tw)
    if arr is None:
        return np.zeros(target, dtype="float64")
    a = np.asarray(arr, dtype="float64")
    while a.ndim > 2:
        a = np.squeeze(a)
    if a.ndim > 2:
        a = np.nanmean(a, axis=tuple(range(2, a.ndim)))
        a = np.asarray(a, dtype="float64")
        while a.ndim > 2:
            a = np.squeeze(a)

    if a.ndim == 0 or a.size == 1:
        val = float(a.reshape(-1)[0]) if a.size else 0.0
        if not np.isfinite(val):
            val = 0.0
        return np.full(target, val, dtype="float64")

    if a.ndim == 1:
        val = float(np.nanmean(a)) if np.isfinite(a).any() else 0.0
        return np.full(target, val, dtype="float64")

    a = _fill_nan_nearest(a)
    if a.shape == target:
        return a
    try:
        from scipy.ndimage import zoom
        zy = th / max(int(a.shape[0]), 1)
        zx = tw / max(int(a.shape[1]), 1)
        out = np.asarray(zoom(a, (zy, zx), order=1), dtype="float64")
        if out.shape != target:
            h = min(th, out.shape[0])
            w = min(tw, out.shape[1])
            dest = np.full(
                target,
                float(np.nanmean(out)) if np.isfinite(out).any() else 0.0,
            )
            dest[:h, :w] = out[:h, :w]
            out = dest
        return _fill_nan_nearest(out)
    except Exception:
        val = float(np.nanmean(a)) if np.isfinite(a).any() else 0.0
        return np.full(target, val, dtype="float64")


def _target_shape_from_bounds(
    bounds: tuple[float, float, float, float],
    resolution_m: float,
) -> tuple[int, int, Any]:
    from rasterio.transform import from_bounds

    minx, miny, maxx, maxy = bounds
    res_deg = resolution_m / 111_320.0
    width = max(2, int(np.ceil((maxx - minx) / res_deg)))
    height = max(2, int(np.ceil((maxy - miny) / res_deg)))
    transform = from_bounds(minx, miny, maxx, maxy, width, height)
    return height, width, transform


def bounds_from_aoi_path(path: str) -> tuple[float, float, float, float]:
    import geopandas as gpd

    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")
    minx, miny, maxx, maxy = gdf.total_bounds
    return float(minx), float(miny), float(maxx), float(maxy)


def resolve_gaul_bounds(
    country: Optional[str] = None,
    adm1: Optional[str] = None,
    adm2: Optional[str] = None,
    adm3: Optional[str] = None,
    gaul_data_dir: str = "data/boundaries/gaul",
    gaul_layer: Optional[str] = None,
) -> tuple[tuple[float, float, float, float], dict]:
    """
    Resolve admin selection to WGS84 bounds with multi-tier fallback:

      1. Local GAUL / boundary files under gaul_data_dir
      2. Nominatim with progressive query simplification
      3. Hardcoded Zimbabwe province / country bboxes (never fail for ZW)

    Always returns a finite bbox for Zimbabwe; raises only for unknown countries
    with no local files and no Nominatim hit.
    """
    def _clean(s: Optional[str]) -> Optional[str]:
        if s is None:
            return None
        s = str(s).strip().strip('"').strip("'")
        return s or None

    country, adm1, adm2, adm3 = map(_clean, (country, adm1, adm2, adm3))
    meta: dict[str, Any] = {
        "country": country, "adm1": adm1, "adm2": adm2, "adm3": adm3, "source": None,
        "fallbacks_tried": [],
        "provinces": [],
    }
    if not country and not adm1:
        raise ValueError("Provide --country and/or --adm1, or use --aoi")

    # Multi-province: "Harare,Bulawayo" or list-like string
    from src.data.zimbabwe_aoi import parse_adm_list, lookup_multi_province_bbox, merge_bboxes
    adm1_parts = parse_adm_list(adm1)
    if len(adm1_parts) > 1:
        meta["provinces"] = adm1_parts
        meta["adm1"] = adm1_parts  # keep list in meta
        # Prefer local GAUL union when possible; else merge hardcoded / Nominatim per province
        boxes = []
        resolved = []
        for prov in adm1_parts:
            try:
                b, m = resolve_gaul_bounds(
                    country=country, adm1=prov, adm2=None, adm3=None,
                    gaul_data_dir=gaul_data_dir, gaul_layer=gaul_layer,
                )
                boxes.append(b)
                resolved.append({"name": prov, "bounds": b, "source": m.get("source")})
            except Exception as exc:
                meta["fallbacks_tried"].append(f"multi:{prov}:{exc}")
        if boxes:
            bounds = merge_bboxes(boxes)
            meta["source"] = "multi_province_merge"
            meta["parts"] = resolved
            logger.info("Multi-province AOI %s → %s", adm1_parts, bounds)
            return bounds, meta
        multi = lookup_multi_province_bbox(country, adm1_parts)
        if multi:
            bounds, label, names = multi
            meta["source"] = label
            meta["provinces"] = names
            logger.warning("Multi-province hardcoded merge %s → %s", names, bounds)
            return bounds, meta

    # ----- 1) Local vector boundaries -----
    data_dir = Path(gaul_data_dir)
    layer_path = Path(gaul_layer) if gaul_layer else None
    if layer_path is None and data_dir.exists():
        for pat in ("*.gpkg", "*.shp", "*.geojson", "**/*.gpkg", "**/*.shp", "**/*.geojson"):
            hits = sorted(data_dir.glob(pat))
            if hits:
                layer_path = hits[0]
                break
    if layer_path is not None and layer_path.exists():
        try:
            import geopandas as gpd
            gdf = gpd.read_file(layer_path)
            if gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")
            else:
                gdf = gdf.to_crs("EPSG:4326")
            cols = {c.lower(): c for c in gdf.columns}

            def _col(*names):
                for n in names:
                    if n.lower() in cols:
                        return cols[n.lower()]
                return None

            c0 = _col("ADM0_NAME", "gaul0_name", "NAME_0", "COUNTRY", "country")
            c1 = _col("ADM1_NAME", "gaul1_name", "NAME_1", "adm1", "province")
            c2 = _col("ADM2_NAME", "gaul2_name", "NAME_2", "adm2", "district")
            c3 = _col("ADM3_NAME", "gaul3_name", "NAME_3", "adm3", "ward")
            mask = np.ones(len(gdf), dtype=bool)
            if c0 and country:
                mask &= gdf[c0].astype(str).str.casefold() == country.casefold()
            if c1 and adm1:
                mask &= gdf[c1].astype(str).str.casefold() == adm1.casefold()
            if c2 and adm2:
                mask &= gdf[c2].astype(str).str.casefold() == adm2.casefold()
            if c3 and adm3:
                mask &= gdf[c3].astype(str).str.casefold() == adm3.casefold()
            sub = gdf[mask]
            if not sub.empty:
                minx, miny, maxx, maxy = sub.total_bounds
                meta["source"] = f"local_gaul:{layer_path}"
                meta["n_features"] = int(len(sub))
                return (float(minx), float(miny), float(maxx), float(maxy)), meta
            meta["fallbacks_tried"].append("local_gaul_no_match")
        except Exception as exc:
            logger.warning("Local GAUL failed: %s", exc)
            meta["fallbacks_tried"].append(f"local_gaul_error:{exc}")

    # ----- 2) Nominatim progressive simplification -----
    import time
    import requests

    query_variants = []
    parts_full = [p for p in (adm3, adm2, adm1, country) if p]
    if parts_full:
        query_variants.append(", ".join(parts_full))
    # drop adm3
    if adm3 and (adm2 or adm1):
        query_variants.append(", ".join([p for p in (adm2, adm1, country) if p]))
    # drop adm2
    if adm1 and country:
        query_variants.append(f"{adm1}, {country}")
    if country:
        query_variants.append(country)
    # dedupe
    seen = set()
    uniq = []
    for q in query_variants:
        if q not in seen:
            seen.add(q)
            uniq.append(q)

    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "HeavyRainfallModel/2.2 (tech-rozvi; research)"}
    for query in uniq:
        meta["fallbacks_tried"].append(f"nominatim:{query}")
        try:
            time.sleep(1.05)  # be polite to Nominatim
            r = requests.get(url, params={"q": query, "format": "json", "limit": 1}, headers=headers, timeout=30)
            r.raise_for_status()
            results = r.json()
            if not results:
                logger.warning("Nominatim empty for '%s'", query)
                continue
            hit = results[0]
            if "boundingbox" in hit:
                south, north, west, east = map(float, hit["boundingbox"])
                bounds = (west, south, east, north)
            else:
                lon, lat = float(hit["lon"]), float(hit["lat"])
                pad = 0.2
                bounds = (lon - pad, lat - pad, lon + pad, lat + pad)
            meta["source"] = "nominatim_osm"
            meta["display_name"] = hit.get("display_name")
            meta["query_used"] = query
            logger.info("Resolved AOI via Nominatim: %s → %s", query, bounds)
            return bounds, meta
        except Exception as exc:
            logger.warning("Nominatim error for '%s': %s", query, exc)

    # ----- 3) Hardcoded Zimbabwe province / country -----
    try:
        from src.data.zimbabwe_aoi import lookup_zimbabwe_bbox
        hit = lookup_zimbabwe_bbox(country, adm1, adm2, adm3)
        if hit is not None:
            bounds, label = hit
            meta["source"] = label
            meta["fallbacks_tried"].append(label)
            logger.warning(
                "Using hardcoded Zimbabwe bbox %s for %s/%s/%s/%s → %s",
                label, country, adm1, adm2, adm3, bounds,
            )
            return bounds, meta
    except Exception as exc:
        logger.warning("Hardcoded ZW lookup failed: %s", exc)

    raise RuntimeError(
        f"Could not resolve AOI for country={country!r} adm1={adm1!r} adm2={adm2!r} adm3={adm3!r}. "
        f"Tried: {meta['fallbacks_tried']}. Provide --aoi GeoJSON or GAUL under data/boundaries/gaul/."
    )


class DataAcquisitionManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.dacfg = cfg.get("data_acquisition", {})
        raw = cfg.get("paths", {}).get("raw_dir", "data/raw")
        self.raw_dir = Path(raw)

    def _make_client(self) -> RemoteDataClient:
        """Instantiate RemoteDataClient with config-driven ERA5 endpoint."""
        atm = self.dacfg.get("atmospheric", {})
        endpoint = atm.get("endpoint", "s3://era5-pds/zarr/")
        requires_auth = bool(atm.get("requires_auth", False))
        cfg = StreamConfig(
            allow_ephemeral_temp=True,
            era5_endpoint=endpoint,
            era5_requires_auth=requires_auth,
        )
        # Must match RemoteDataClient.__init__(self, config=None, **kwargs)
        return RemoteDataClient(config=cfg)

    def acquire(
        self,
        mode: str = "api",
        aoi_bounds: Optional[tuple[float, float, float, float]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        resolution_m: Optional[float] = None,
    ) -> AcquisitionResult:
        mode = (mode or self.dacfg.get("mode", "api")).lower()
        if mode in ("api", "stream", "remote", "auto"):
            if aoi_bounds is None:
                raise ValueError(
                    "API mode requires AOI bounds (--aoi or --country / GAUL selection). "
                    "Synthetic fallback is disabled."
                )
            start_date = start_date or self.cfg.get("time", {}).get("start_date", "2015-01-01")
            end_date = end_date or self.cfg.get("time", {}).get("end_date", "2020-12-31")
            resolution_m = float(
                resolution_m
                or self.cfg.get("study_area", {}).get("target_resolution_m", CHIRPS_RESOLUTION_M)
            )
            resolution_m = max(resolution_m, CHIRPS_RESOLUTION_M)
            return self.acquire_remote(aoi_bounds, start_date, end_date, resolution_m)
        return self.acquire_local()

    def acquire_local(self) -> AcquisitionResult:
        raw = self.raw_dir
        precip_path = raw / "daily_precip.npy"
        dem_path = raw / "dem.tif"
        if not precip_path.exists():
            raise FileNotFoundError(
                f"Missing {precip_path}. Place real data or use --mode api "
                "with --aoi / --country. Synthetic auto-generation is disabled."
            )
        if not dem_path.exists():
            raise FileNotFoundError(f"Missing {dem_path}.")

        import rasterio

        daily = np.load(precip_path)
        with rasterio.open(dem_path) as src:
            dem = src.read(1).astype("float64")
            transform = src.transform
            crs = str(src.crs) if src.crs else "EPSG:4326"
            resolution_m = abs(src.transform.a)

        def _tif(name: str) -> np.ndarray:
            p = raw / f"{name}.tif"
            if not p.exists():
                raise FileNotFoundError(
                    f"Missing required raster {p}. Synthetic fill is disabled."
                )
            return read_geotiff(p).data.astype("float64")

        temperature = _tif("temperature")
        rh = _tif("relative_humidity")
        wind = _tif("wind_speed")
        dist = _tif("distance_to_coast")

        slope, aspect_deg = terr.compute_slope_aspect(dem, cellsize_m=float(resolution_m))
        wind_from = float(
            self.cfg.get("factors", {})
            .get("terrain_factors", {})
            .get("aspect_exposure", {})
            .get("dominant_wind_from_deg", 90.0)
        )
        aspect = terr.windward_exposure(aspect_deg, dominant_wind_from_deg=wind_from)
        n_years = float(
            self.cfg.get("time", {}).get(
                "n_years_hint", max(1.0, daily.shape[0] / 365.25)
            )
        )

        return AcquisitionResult(
            daily_precip=daily,
            n_years=n_years,
            dem=dem,
            slope=slope,
            aspect_exposure=aspect,
            temperature=temperature,
            relative_humidity=rh,
            wind_speed=wind,
            distance_to_coast=dist,
            transform=transform,
            crs=crs,
            resolution_m=float(resolution_m),
            mode="local",
            sources={"mode": "local", "raw_dir": str(raw)},
        )

    def acquire_remote(
        self,
        bounds: tuple[float, float, float, float],
        start_date: str,
        end_date: str,
        resolution_m: float = CHIRPS_RESOLUTION_M,
    ) -> AcquisitionResult:
        """
        Stream real data for AOI + period with per-layer fallbacks.

        Critical layers (precip, DEM) still raise if every source fails.
        Atmospheric / coast degrade to Open-Meteo or distance proxy with warnings
        so a full pipeline run can complete for Zimbabwe QA AOIs.
        """
        client = self._make_client()
        sources: dict[str, Any] = {"warnings": []}

        # ---- CHIRPS (historical only; optional for forecast-mode DEM pulls) ----
        use_chirps, chirps_reason = _dates_need_chirps(start_date, end_date)
        precip = None
        if not use_chirps:
            logger.info(
                "REMOTE — skipping CHIRPS (%s). Forecast/QPF path does not need historical precip.",
                chirps_reason,
            )
            sources["warnings"].append(f"chirps_skipped:{chirps_reason}")
            precip = {
                "precipitation": np.zeros((1, 1, 1), dtype="float64"),
                "dates": [str(start_date)[:10]],
                "source": {
                    "provider": "skipped",
                    "reason": chirps_reason,
                    "note": "Historical CHIRPS not requested for this date window",
                },
            }
        else:
            logger.info("REMOTE — CHIRPS %s → %s", start_date, end_date)
            for attempt in range(3):
                try:
                    precip = client.fetch_chirps_daily(bounds, start_date, end_date)
                    break
                except Exception as exc:
                    logger.warning("CHIRPS attempt %d failed: %s", attempt + 1, exc)
                    sources["warnings"].append(f"chirps:{exc}")
            if precip is None:
                try:
                    precip = client.fetch_precip_open_meteo(bounds, start_date, end_date)
                    sources["warnings"].append("chirps_replaced_by_open_meteo")
                except Exception as exc:
                    raise RuntimeError(
                        f"Precipitation unavailable (CHIRPS and Open-Meteo failed): {exc}"
                    ) from exc
        sources["precipitation"] = precip.get("source", {})

        # ---- DEM (required) ----
        logger.info("REMOTE — Copernicus DEM")
        dem_r = None
        for attempt in range(2):
            try:
                dem_r = client.fetch_dem(bounds)
                break
            except Exception as exc:
                logger.warning("DEM attempt %d failed: %s", attempt + 1, exc)
                sources["warnings"].append(f"dem:{exc}")
        if dem_r is None:
            raise RuntimeError(
                "DEM unavailable after retries. Check network / AOI size. "
                "Synthetic DEM is disabled."
            )
        sources["dem"] = dem_r.get("source", {})

        # ---- Atmosphere (soft) ----
        logger.info("REMOTE — atmospheric (ERA5 / Open-Meteo)")
        try:
            atm = client.fetch_era5_land_climatology(bounds, start_date, end_date)
        except Exception as exc:
            logger.warning("Atmosphere stream failed (%s); using Open-Meteo only", exc)
            try:
                atm = client._era5_open_meteo(bounds, start_date, end_date)
                sources["warnings"].append(f"atmosphere_fallback:{exc}")
            except Exception as exc2:
                logger.warning("Open-Meteo atmosphere failed (%s); neutral fields", exc2)
                # Minimal real-ish neutral climatology from tropical highland defaults
                # Marked as degraded — not synthetic random fields
                atm = {
                    "temperature": np.array([[20.0]]),
                    "relative_humidity": np.array([[60.0]]),
                    "wind_speed": np.array([[3.0]]),
                    "source": {"provider": "degraded_default", "note": str(exc2)},
                }
                sources["warnings"].append("atmosphere_degraded_defaults")
        sources["atmospheric"] = atm.get("source", {})

        # ---- Coast (soft) ----
        logger.info("REMOTE — coastline distance")
        try:
            coast = client.fetch_distance_to_coast(bounds, resolution_m)
        except Exception as exc:
            logger.warning("Coastline failed (%s); using distance-from-bbox-edge proxy", exc)
            th, tw, target_transform = _target_shape_from_bounds(bounds, resolution_m)
            # Rough proxy: distance from domain centre (km) — finite, aligned
            yy, xx = np.mgrid[0:th, 0:tw]
            cy, cx = (th - 1) / 2.0, (tw - 1) / 2.0
            dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2) * (resolution_m / 1000.0)
            coast = {
                "distance_to_coast": dist,
                "transform": target_transform,
                "source": {"provider": "proxy_bbox", "warning": str(exc)},
            }
            sources["warnings"].append(f"coast_proxy:{exc}")
        sources["coast"] = coast.get("source", {})

        daily = np.asarray(precip["precipitation"], dtype="float64")
        if daily.ndim == 1:
            daily = daily.reshape(-1, 1, 1)
        n_years = max(1.0, daily.shape[0] / 365.25)
        dates = list(precip.get("dates") or [])

        th, tw, target_transform = _target_shape_from_bounds(bounds, resolution_m)
        target = (th, tw)
        if daily.ndim == 3:
            if daily.shape[1:] != target and not (daily.shape[1] == 1 and daily.shape[2] == 1):
                stacked = [_fit_to_shape(daily[i], target) for i in range(daily.shape[0])]
                daily = np.stack(stacked, axis=0)
            spatial = daily.shape[1:] if daily.shape[1] > 1 else target
        else:
            spatial = target

        dem = _fill_nan_nearest(_fit_to_shape(dem_r["elevation"], spatial))
        temperature = _fill_nan_nearest(_fit_to_shape(np.squeeze(atm["temperature"]), spatial))
        rh = _fill_nan_nearest(_fit_to_shape(np.squeeze(atm["relative_humidity"]), spatial))
        wind = _fill_nan_nearest(_fit_to_shape(np.squeeze(atm["wind_speed"]), spatial))
        dist = _fill_nan_nearest(_fit_to_shape(coast["distance_to_coast"], spatial))

        # Guard non-finite
        dem = np.nan_to_num(dem, nan=float(np.nanmean(dem) if np.isfinite(dem).any() else 1000.0))
        temperature = np.nan_to_num(temperature, nan=20.0)
        rh = np.clip(np.nan_to_num(rh, nan=60.0), 0, 100)
        wind = np.nan_to_num(wind, nan=2.0)
        dist = np.nan_to_num(dist, nan=100.0)
        daily = np.nan_to_num(daily, nan=0.0)
        daily = np.maximum(daily, 0.0)

        slope, aspect_deg = terr.compute_slope_aspect(dem, cellsize_m=float(resolution_m))
        wind_from = float(
            self.cfg.get("factors", {})
            .get("terrain_factors", {})
            .get("aspect_exposure", {})
            .get("dominant_wind_from_deg", 90.0)
        )
        aspect = terr.windward_exposure(aspect_deg, dominant_wind_from_deg=wind_from)

        transform = (
            precip.get("transform")
            or dem_r.get("transform")
            or coast.get("transform")
            or target_transform
        )

        return AcquisitionResult(
            daily_precip=daily,
            n_years=n_years,
            dem=dem,
            slope=np.nan_to_num(slope, nan=0.0),
            aspect_exposure=np.nan_to_num(aspect, nan=0.5),
            temperature=temperature,
            relative_humidity=rh,
            wind_speed=wind,
            distance_to_coast=dist,
            transform=transform,
            crs="EPSG:4326",
            resolution_m=float(resolution_m),
            mode="api",
            sources=sources,
            dates=dates,
        )