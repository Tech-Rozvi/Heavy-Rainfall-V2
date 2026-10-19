"""
multi_peril.py — Dynamic pluvial / fluvial / coastal boundary forcing.

Fluvial: rasterise HydroRIVERS/OSM line GeoJSON/Shapefile onto the DEM grid
and inject Q(t) as mass + momentum sources on channel cells.

Coastal: time-series η(t) = tide + surge + SLR (array or callable), applied
as dynamic head BCs on ocean-edge cells — not a single static level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Union

import numpy as np

from src.utils import get_logger
from .solver2d import SolverState

logger = get_logger(__name__)

MM_H_TO_M_S = 1.0 / 3_600_000.0
TimeSeries = Union[Callable[[float], float], np.ndarray, Sequence[float]]


@dataclass
class PerilConfig:
    enable_pluvial: bool = True
    enable_fluvial: bool = True
    enable_coastal: bool = True
    curve_number: float = 75.0
    cn_map: Optional[np.ndarray] = None
    initial_abstraction_ratio: float = 0.2
    use_green_ampt: bool = False
    suction_head_m: float = 0.1
    hydraulic_conductivity_m_s: float = 1e-6
    theta_deficit: float = 0.2


# Canonical hydrograph lives in src.hydrology (Phase 4 separation of concerns)
try:
    from src.hydrology.hydrograph import Hydrograph
except ImportError:  # pragma: no cover
    @dataclass
    class Hydrograph:  # type: ignore
        """Fallback piecewise-linear discharge Q(t) [m³/s]."""
        times_s: np.ndarray
        discharge_m3s: np.ndarray

        def q_at(self, t: float) -> float:
            ts = np.asarray(self.times_s, dtype="float64")
            qs = np.asarray(self.discharge_m3s, dtype="float64")
            t = float(t)
            if t <= ts[0]:
                return float(qs[0])
            if t >= ts[-1]:
                return float(qs[-1])
            return float(np.interp(t, ts, qs))

        @classmethod
        def from_arrays(cls, times_s: Sequence[float], q_m3s: Sequence[float]) -> "Hydrograph":
            return cls(np.asarray(times_s, dtype="float64"), np.asarray(q_m3s, dtype="float64"))


@dataclass
class FluvialInflow:
    row_idx: np.ndarray
    col_idx: np.ndarray
    hydrograph: Hydrograph
    dir_u: float = 1.0
    dir_v: float = 0.0


@dataclass
class CoastalBoundary:
    """
    Dynamic ocean head boundary.

    ``level_series`` may be:
    - callable(t_seconds) -> η metres
    - 1-D array sampled at ``dt_s`` starting at t=0
    - Hydrograph-like object with ``q_at`` renamed conceptually as level
    """

    row_idx: np.ndarray
    col_idx: np.ndarray
    level_series: TimeSeries
    dt_s: float = 1.0  # only used if level_series is an array

    def eta_at(self, t: float) -> float:
        s = self.level_series
        if callable(s):
            return float(s(t))
        arr = np.asarray(s, dtype="float64").ravel()
        if arr.size == 0:
            return 0.0
        idx = int(np.clip(t / max(self.dt_s, 1e-9), 0, arr.size - 1))
        # linear interpolate between samples
        i0 = min(idx, arr.size - 1)
        i1 = min(i0 + 1, arr.size - 1)
        t0 = i0 * self.dt_s
        if i0 == i1 or self.dt_s <= 0:
            return float(arr[i0])
        w = (t - t0) / self.dt_s
        return float((1 - w) * arr[i0] + w * arr[i1])


@dataclass
class MultiPerilForcing:
    rain_mm_per_hour: Any = 0.0
    config: PerilConfig = field(default_factory=PerilConfig)
    fluvial_inflows: Sequence[FluvialInflow] = field(default_factory=list)
    coastal: Optional[CoastalBoundary] = None
    cell_area_m2: float = 900.0
    _P_cum_mm: float = field(default=0.0, init=False, repr=False)
    _last_t: float = field(default=0.0, init=False, repr=False)

    def rain_at(self, t: float, state: SolverState) -> np.ndarray:
        if not self.config.enable_pluvial:
            return np.zeros_like(state.h)
        return self._eval_rain(t, state.h.shape) * MM_H_TO_M_S

    def infiltration_at(self, t: float, state: SolverState) -> np.ndarray:
        if not self.config.enable_pluvial:
            return np.zeros_like(state.h)
        rain_mm_h = self._eval_rain(t, state.h.shape)
        rain_m_s = rain_mm_h * MM_H_TO_M_S
        dt = max(t - self._last_t, 0.0)
        self._P_cum_mm += float(np.nanmean(rain_mm_h)) * (dt / 3600.0)
        self._last_t = t
        if self.config.use_green_ampt:
            return self._green_ampt(rain_m_s, state)
        return self._scs_cn(rain_m_s, state)

    def fluvial_mass_source(self, t: float, shape: tuple[int, int]) -> np.ndarray:
        src = np.zeros(shape, dtype="float64")
        if not self.config.enable_fluvial:
            return src
        area = max(self.cell_area_m2, 1.0)
        for inflow in self.fluvial_inflows:
            q_per = inflow.hydrograph.q_at(t) / (max(len(inflow.row_idx), 1) * area)
            rr = np.asarray(inflow.row_idx, dtype=int)
            cc = np.asarray(inflow.col_idx, dtype=int)
            m = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
            np.add.at(src, (rr[m], cc[m]), q_per)
        return src

    def momentum_source(self, t: float, state: SolverState) -> tuple[np.ndarray, np.ndarray]:
        hu_s = np.zeros_like(state.h)
        hv_s = np.zeros_like(state.h)
        if not self.config.enable_fluvial:
            return hu_s, hv_s
        area = max(self.cell_area_m2, 1.0)
        for inflow in self.fluvial_inflows:
            q_per = inflow.hydrograph.q_at(t) / (max(len(inflow.row_idx), 1) * area)
            rr = np.asarray(inflow.row_idx, dtype=int)
            cc = np.asarray(inflow.col_idx, dtype=int)
            m = (rr >= 0) & (rr < state.h.shape[0]) & (cc >= 0) & (cc < state.h.shape[1])
            np.add.at(hu_s, (rr[m], cc[m]), q_per * inflow.dir_u)
            np.add.at(hv_s, (rr[m], cc[m]), q_per * inflow.dir_v)
        return hu_s, hv_s

    def apply_boundary_depths(self, state: SolverState) -> None:
        """Dynamic coastal head: h = max(η(t) − z, 0) on ocean cells."""
        if not self.config.enable_coastal or self.coastal is None:
            return
        eta = self.coastal.eta_at(state.time)
        rr = np.asarray(self.coastal.row_idx, dtype=int)
        cc = np.asarray(self.coastal.col_idx, dtype=int)
        for r, c in zip(rr, cc):
            if 0 <= r < state.h.shape[0] and 0 <= c < state.h.shape[1]:
                z = state.z[r, c]
                if np.isfinite(z):
                    state.h[r, c] = max(eta - z, 0.0)
                    state.hu[r, c] = 0.0
                    state.hv[r, c] = 0.0

    def _scs_cn(self, rain_m_s: np.ndarray, state: SolverState) -> np.ndarray:
        cfg = self.config
        cn = cfg.cn_map if cfg.cn_map is not None else cfg.curve_number
        cn_arr = np.asarray(cn, dtype="float64")
        if cn_arr.ndim == 0:
            cn_arr = np.full(state.h.shape, float(cn_arr))
        cn_arr = np.clip(cn_arr, 30.0, 98.0)
        S = 25400.0 / cn_arr - 254.0
        Ia_m = float(np.nanmean(cfg.initial_abstraction_ratio * S))
        S_m = float(np.nanmean(S))
        P = self._P_cum_mm
        if P <= Ia_m:
            runoff_frac = 0.0
        else:
            num = (P - Ia_m) * (P - Ia_m + 2 * S_m)
            den = (P - Ia_m + S_m) ** 2
            runoff_frac = float(np.clip(num / max(den, 1e-6), 0.0, 1.0))
        return np.maximum(rain_m_s * (1.0 - runoff_frac), 0.0)

    def _green_ampt(self, rain_m_s: np.ndarray, state: SolverState) -> np.ndarray:
        cfg = self.config
        h_mean = float(np.nanmean(state.h)) + 1e-3
        f_pot = cfg.hydraulic_conductivity_m_s * (
            1.0 + cfg.suction_head_m * cfg.theta_deficit / h_mean
        )
        return np.minimum(np.maximum(rain_m_s, 0.0), f_pot)

    def _eval_rain(self, t: float, shape: tuple[int, int]) -> np.ndarray:
        r = self.rain_mm_per_hour
        val = r(t) if callable(r) else r
        if np.isscalar(val):
            return np.full(shape, float(val), dtype="float64")
        arr = np.asarray(val, dtype="float64")
        if arr.shape != shape:
            raise ValueError(f"Rain map {arr.shape} != {shape}")
        return np.where(np.isfinite(arr), arr, 0.0)


def rasterize_river_network(
    river_path: str | Path,
    dem_shape: tuple[int, int],
    transform: Any,
    crs: str = "EPSG:4326",
    all_touched: bool = True,
) -> np.ndarray:
    """
    Burn river linework (GeoJSON/Shapefile/GPKG) onto a boolean mask
    aligned with the DEM grid (rasterio transform).
    """
    import geopandas as gpd
    from rasterio import features

    path = Path(river_path)
    if not path.exists():
        raise FileNotFoundError(path)
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(crs)
    else:
        gdf = gdf.to_crs(crs)
    shapes = [(geom, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty]
    if not shapes:
        logger.warning("No river geometries in %s", path)
        return np.zeros(dem_shape, dtype=bool)
    mask = features.rasterize(
        shapes,
        out_shape=dem_shape,
        transform=transform,
        fill=0,
        all_touched=all_touched,
        dtype="uint8",
    )
    logger.info("Rasterised %d river features → %d cells", len(shapes), int(mask.sum()))
    return mask.astype(bool)


def rasterize_coastline_edge(
    coast_path: str | Path,
    dem_shape: tuple[int, int],
    transform: Any,
    dem: np.ndarray,
    max_elev_m: float = 2.0,
    crs: str = "EPSG:4326",
) -> np.ndarray:
    """
    Coastal BC cells = low-elevation DEM cells near a coastline vector,
    or simply DEM cells below ``max_elev_m`` on the domain edge if no file.
    """
    ny, nx = dem_shape
    edge = np.zeros(dem_shape, dtype=bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    low = np.isfinite(dem) & (dem <= max_elev_m)
    mask = edge & low
    path = Path(coast_path) if coast_path else None
    if path is not None and path.exists():
        try:
            import geopandas as gpd
            from rasterio import features

            gdf = gpd.read_file(path)
            if gdf.crs is None:
                gdf = gdf.set_crs(crs)
            else:
                gdf = gdf.to_crs(crs)
            shapes = [(g, 1) for g in gdf.geometry if g is not None]
            burned = features.rasterize(
                shapes, out_shape=dem_shape, transform=transform,
                fill=0, all_touched=True, dtype="uint8",
            ).astype(bool)
            mask = burned & low
        except Exception as exc:
            logger.warning("Coast rasterise failed (%s); using DEM edge", exc)
    return mask


def build_forcing_from_layers(
    *,
    dem: np.ndarray,
    dx: float,
    dy: float,
    rain_mm_per_hour: Any = 0.0,
    cn_map: Optional[np.ndarray] = None,
    river_mask: Optional[np.ndarray] = None,
    river_path: Optional[str | Path] = None,
    river_hydrograph: Optional[Hydrograph] = None,
    transform: Any = None,
    coastal_mask: Optional[np.ndarray] = None,
    coastal_level_series: Optional[TimeSeries] = None,
    coastal_dt_s: float = 60.0,
    curve_number: float = 75.0,
) -> MultiPerilForcing:
    """
    Build multi-peril forcing. Prefer ``river_path`` (vector) when mask absent.
    ``coastal_level_series`` is a dynamic η(t) time series (not a constant).
    """
    if river_mask is None and river_path is not None and transform is not None:
        river_mask = rasterize_river_network(river_path, dem.shape, transform)

    cfg = PerilConfig(
        curve_number=curve_number,
        cn_map=cn_map,
        enable_fluvial=river_mask is not None and river_hydrograph is not None,
        enable_coastal=coastal_mask is not None and coastal_level_series is not None,
    )
    fluvial: list[FluvialInflow] = []
    if cfg.enable_fluvial and river_mask is not None and river_hydrograph is not None:
        rows, cols = np.where(np.asarray(river_mask, dtype=bool))
        if rows.size:
            fluvial.append(FluvialInflow(rows.astype(int), cols.astype(int), river_hydrograph))

    coastal = None
    if cfg.enable_coastal and coastal_mask is not None and coastal_level_series is not None:
        rows, cols = np.where(np.asarray(coastal_mask, dtype=bool))
        coastal = CoastalBoundary(
            row_idx=rows.astype(int),
            col_idx=cols.astype(int),
            level_series=coastal_level_series,
            dt_s=float(coastal_dt_s),
        )

    return MultiPerilForcing(
        rain_mm_per_hour=rain_mm_per_hour,
        config=cfg,
        fluvial_inflows=fluvial,
        coastal=coastal,
        cell_area_m2=float(dx * dy),
    )
