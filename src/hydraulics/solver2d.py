"""
solver2d.py — Memory-conscious 2D SWE finite-volume solver.

HLL Godunov fluxes with optional Numba JIT (@njit fastmath). Adaptive CFL
time step uses peak |u|+c and a mild terrain-steepness penalty so steep
FABDEM tiles do not violate stability as quickly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

G = 9.80665
EPS_H = 1e-4

try:
    from numba import njit
    _HAS_NUMBA = True
except ImportError:  # pragma: no cover
    _HAS_NUMBA = False

    def njit(*args, **kwargs):  # type: ignore
        def deco(fn):
            return fn
        if args and callable(args[0]):
            return args[0]
        return deco


@dataclass
class SolverConfig:
    dx: float = 30.0
    dy: float = 30.0
    manning_n: float = 0.03
    cfl: float = 0.35
    max_dt: float = 5.0
    min_dt: float = 0.02
    h_dry: float = EPS_H
    theta: float = 1.0
    use_numba: bool = True
    max_steps: int = 500_000
    record_every: int = 50
    nodata: float = -9999.0
    # Extra CFL tightening when |∇z| is large (dimensionless slope)
    steepness_cfl_factor: float = 0.5
    steepness_slope_threshold: float = 0.15


@dataclass
class SolverState:
    h: np.ndarray
    hu: np.ndarray
    hv: np.ndarray
    z: np.ndarray
    n_manning: np.ndarray
    time: float = 0.0
    step: int = 0
    h_max: Optional[np.ndarray] = None

    def velocity(self, h_dry: float = EPS_H) -> Tuple[np.ndarray, np.ndarray]:
        wet = self.h > h_dry
        hs = np.maximum(self.h, h_dry)
        return (
            np.where(wet, self.hu / hs, 0.0),
            np.where(wet, self.hv / hs, 0.0),
        )


@njit(cache=True, fastmath=True)
def _hll_x_numba(h, hu, hv, z, h_dry):
    ny, nx = h.shape
    fx_h = np.zeros((ny, nx - 1))
    fx_hu = np.zeros((ny, nx - 1))
    fx_hv = np.zeros((ny, nx - 1))
    for i in range(ny):
        for j in range(nx - 1):
            hL = h[i, j]
            hR = h[i, j + 1]
            if hL != hL:
                hL = 0.0
            if hR != hR:
                hR = 0.0
            if hL < 0.0:
                hL = 0.0
            if hR < 0.0:
                hR = 0.0
            zL = z[i, j]
            zR = z[i, j + 1]
            if zL != zL:
                zL = 0.0
            if zR != zR:
                zR = 0.0
            z_int = zL if zL > zR else zR
            hL_r = hL + zL - z_int
            hR_r = hR + zR - z_int
            if hL_r < 0.0:
                hL_r = 0.0
            if hR_r < 0.0:
                hR_r = 0.0
            uL = hu[i, j] / hL if hL > h_dry else 0.0
            vL = hv[i, j] / hL if hL > h_dry else 0.0
            uR = hu[i, j + 1] / hR if hR > h_dry else 0.0
            vR = hv[i, j + 1] / hR if hR > h_dry else 0.0
            cL = (G * hL_r) ** 0.5
            cR = (G * hR_r) ** 0.5
            sL = uL - cL
            sR = uR + cR
            if (uR - cR) < sL:
                sL = uR - cR
            if (uL + cL) > sR:
                sR = uL + cL
            if sL > 0.0:
                sL = 0.0
            if sR < 0.0:
                sR = 0.0
            fLh = hL_r * uL
            fRh = hR_r * uR
            fLhu = hL_r * uL * uL + 0.5 * G * hL_r * hL_r
            fRhu = hR_r * uR * uR + 0.5 * G * hR_r * hR_r
            fLhv = hL_r * uL * vL
            fRhv = hR_r * uR * vR
            if sL >= 0.0:
                fx_h[i, j] = fLh
                fx_hu[i, j] = fLhu
                fx_hv[i, j] = fLhv
            elif sR <= 0.0:
                fx_h[i, j] = fRh
                fx_hu[i, j] = fRhu
                fx_hv[i, j] = fRhv
            else:
                den = sR - sL
                if den < 1e-14 and den > -1e-14:
                    den = 1.0
                fx_h[i, j] = (sR * fLh - sL * fRh + sL * sR * (hR_r - hL_r)) / den
                fx_hu[i, j] = (sR * fLhu - sL * fRhu + sL * sR * (hR_r * uR - hL_r * uL)) / den
                fx_hv[i, j] = (sR * fLhv - sL * fRhv + sL * sR * (hR_r * vR - hL_r * vL)) / den
    return fx_h, fx_hu, fx_hv


@njit(cache=True, fastmath=True)
def _hll_y_numba(h, hu, hv, z, h_dry):
    ny, nx = h.shape
    fy_h = np.zeros((ny - 1, nx))
    fy_hu = np.zeros((ny - 1, nx))
    fy_hv = np.zeros((ny - 1, nx))
    for i in range(ny - 1):
        for j in range(nx):
            hL = h[i, j]
            hR = h[i + 1, j]
            if hL != hL:
                hL = 0.0
            if hR != hR:
                hR = 0.0
            if hL < 0.0:
                hL = 0.0
            if hR < 0.0:
                hR = 0.0
            zL = z[i, j]
            zR = z[i + 1, j]
            if zL != zL:
                zL = 0.0
            if zR != zR:
                zR = 0.0
            z_int = zL if zL > zR else zR
            hL_r = hL + zL - z_int
            hR_r = hR + zR - z_int
            if hL_r < 0.0:
                hL_r = 0.0
            if hR_r < 0.0:
                hR_r = 0.0
            uL = hu[i, j] / hL if hL > h_dry else 0.0
            vL = hv[i, j] / hL if hL > h_dry else 0.0
            uR = hu[i + 1, j] / hR if hR > h_dry else 0.0
            vR = hv[i + 1, j] / hR if hR > h_dry else 0.0
            cL = (G * hL_r) ** 0.5
            cR = (G * hR_r) ** 0.5
            sL = vL - cL
            sR = vR + cR
            if (vR - cR) < sL:
                sL = vR - cR
            if (vL + cL) > sR:
                sR = vL + cL
            if sL > 0.0:
                sL = 0.0
            if sR < 0.0:
                sR = 0.0
            fLh = hL_r * vL
            fRh = hR_r * vR
            fLhv = hL_r * vL * vL + 0.5 * G * hL_r * hL_r
            fRhv = hR_r * vR * vR + 0.5 * G * hR_r * hR_r
            fLhu = hL_r * vL * uL
            fRhu = hR_r * vR * uR
            if sL >= 0.0:
                fy_h[i, j] = fLh
                fy_hu[i, j] = fLhu
                fy_hv[i, j] = fLhv
            elif sR <= 0.0:
                fy_h[i, j] = fRh
                fy_hu[i, j] = fRhu
                fy_hv[i, j] = fRhv
            else:
                den = sR - sL
                if den < 1e-14 and den > -1e-14:
                    den = 1.0
                fy_h[i, j] = (sR * fLh - sL * fRh + sL * sR * (hR_r - hL_r)) / den
                fy_hv[i, j] = (sR * fLhv - sL * fRhv + sL * sR * (hR_r * vR - hL_r * vL)) / den
                fy_hu[i, j] = (sR * fLhu - sL * fRhu + sL * sR * (hR_r * uR - hL_r * uL)) / den
    return fy_h, fy_hu, fy_hv


def _hll_x_numpy(h, hu, hv, z, h_dry):
    hL, hR = np.maximum(np.nan_to_num(h[:, :-1], nan=0.0), 0.0), np.maximum(np.nan_to_num(h[:, 1:], nan=0.0), 0.0)
    zL, zR = np.nan_to_num(z[:, :-1], nan=0.0), np.nan_to_num(z[:, 1:], nan=0.0)
    huL, huR = hu[:, :-1], hu[:, 1:]
    hvL, hvR = hv[:, :-1], hv[:, 1:]
    z_int = np.fmax(zL, zR)
    hL_r = np.maximum(hL + zL - z_int, 0.0)
    hR_r = np.maximum(hR + zR - z_int, 0.0)
    uL = np.where(hL > h_dry, huL / np.maximum(hL, h_dry), 0.0)
    vL = np.where(hL > h_dry, hvL / np.maximum(hL, h_dry), 0.0)
    uR = np.where(hR > h_dry, huR / np.maximum(hR, h_dry), 0.0)
    vR = np.where(hR > h_dry, hvR / np.maximum(hR, h_dry), 0.0)
    cL, cR = np.sqrt(G * hL_r), np.sqrt(G * hR_r)
    sL = np.minimum(np.minimum(uL - cL, uR - cR), 0.0)
    sR = np.maximum(np.maximum(uL + cL, uR + cR), 0.0)
    fLh, fRh = hL_r * uL, hR_r * uR
    fLhu = hL_r * uL * uL + 0.5 * G * hL_r ** 2
    fRhu = hR_r * uR * uR + 0.5 * G * hR_r ** 2
    fLhv, fRhv = hL_r * uL * vL, hR_r * uR * vR
    den = np.where(np.abs(sR - sL) < 1e-14, 1.0, sR - sL)
    flux_h = np.where(sL >= 0, fLh, np.where(sR <= 0, fRh, (sR * fLh - sL * fRh + sL * sR * (hR_r - hL_r)) / den))
    flux_hu = np.where(sL >= 0, fLhu, np.where(sR <= 0, fRhu, (sR * fLhu - sL * fRhu + sL * sR * (hR_r * uR - hL_r * uL)) / den))
    flux_hv = np.where(sL >= 0, fLhv, np.where(sR <= 0, fRhv, (sR * fLhv - sL * fRhv + sL * sR * (hR_r * vR - hL_r * vL)) / den))
    return flux_h, flux_hu, flux_hv


def _hll_y_numpy(h, hu, hv, z, h_dry):
    hL, hR = np.maximum(np.nan_to_num(h[:-1, :], nan=0.0), 0.0), np.maximum(np.nan_to_num(h[1:, :], nan=0.0), 0.0)
    zL, zR = np.nan_to_num(z[:-1, :], nan=0.0), np.nan_to_num(z[1:, :], nan=0.0)
    huL, huR = hu[:-1, :], hu[1:, :]
    hvL, hvR = hv[:-1, :], hv[1:, :]
    z_int = np.fmax(zL, zR)
    hL_r = np.maximum(hL + zL - z_int, 0.0)
    hR_r = np.maximum(hR + zR - z_int, 0.0)
    uL = np.where(hL > h_dry, huL / np.maximum(hL, h_dry), 0.0)
    vL = np.where(hL > h_dry, hvL / np.maximum(hL, h_dry), 0.0)
    uR = np.where(hR > h_dry, huR / np.maximum(hR, h_dry), 0.0)
    vR = np.where(hR > h_dry, hvR / np.maximum(hR, h_dry), 0.0)
    cL, cR = np.sqrt(G * hL_r), np.sqrt(G * hR_r)
    sL = np.minimum(np.minimum(vL - cL, vR - cR), 0.0)
    sR = np.maximum(np.maximum(vL + cL, vR + cR), 0.0)
    fLh, fRh = hL_r * vL, hR_r * vR
    fLhv = hL_r * vL * vL + 0.5 * G * hL_r ** 2
    fRhv = hR_r * vR * vR + 0.5 * G * hR_r ** 2
    fLhu, fRhu = hL_r * vL * uL, hR_r * vR * uR
    den = np.where(np.abs(sR - sL) < 1e-14, 1.0, sR - sL)
    flux_h = np.where(sL >= 0, fLh, np.where(sR <= 0, fRh, (sR * fLh - sL * fRh + sL * sR * (hR_r - hL_r)) / den))
    flux_hv = np.where(sL >= 0, fLhv, np.where(sR <= 0, fRhv, (sR * fLhv - sL * fRhv + sL * sR * (hR_r * vR - hL_r * vL)) / den))
    flux_hu = np.where(sL >= 0, fLhu, np.where(sR <= 0, fRhu, (sR * fLhu - sL * fRhu + sL * sR * (hR_r * uR - hL_r * uL)) / den))
    return flux_h, flux_hu, flux_hv


class ShallowWater2D:
    def __init__(
        self,
        dem: np.ndarray,
        config: Optional[SolverConfig] = None,
        manning: Optional[np.ndarray | float] = None,
    ):
        self.cfg = config or SolverConfig()
        z = np.asarray(dem, dtype="float64")
        if z.ndim != 2:
            raise ValueError(f"DEM must be 2-D, got {z.shape}")
        self.ny, self.nx = z.shape
        self.valid = np.isfinite(z) & (z != self.cfg.nodata)
        self.z = np.where(self.valid, z, np.nan)
        if manning is None:
            n_map = np.full(z.shape, self.cfg.manning_n, dtype="float64")
        elif np.isscalar(manning):
            n_map = np.full(z.shape, float(manning), dtype="float64")
        else:
            n_map = np.asarray(manning, dtype="float64")
            if n_map.shape != z.shape:
                raise ValueError("Manning map shape mismatch")
        self.n_manning = np.where(self.valid, np.clip(n_map, 0.01, 0.25), self.cfg.manning_n)
        # Precompute max bed slope for CFL penalty
        zt = np.nan_to_num(self.z, nan=0.0)
        sx = np.abs(np.gradient(zt, self.cfg.dx, axis=1))
        sy = np.abs(np.gradient(zt, self.cfg.dy, axis=0))
        self._max_slope = float(np.nanmax(np.where(self.valid, np.maximum(sx, sy), 0.0)))
        self._use_numba = bool(self.cfg.use_numba and _HAS_NUMBA)
        if self.cfg.use_numba and not _HAS_NUMBA:
            logger.warning("Numba not installed; using NumPy HLL fluxes.")
        self.reset()

    def reset(self, h0: Optional[np.ndarray] = None) -> SolverState:
        shape = (self.ny, self.nx)
        h = np.zeros(shape) if h0 is None else np.maximum(np.asarray(h0, dtype="float64"), 0.0)
        h = np.where(self.valid, h, 0.0)
        self.state = SolverState(
            h=h, hu=np.zeros(shape), hv=np.zeros(shape),
            z=self.z.copy(), n_manning=self.n_manning.copy(), h_max=h.copy(),
        )
        return self.state

    def step(
        self,
        dt: Optional[float] = None,
        rain_rate: Optional[np.ndarray | float] = None,
        infiltration_rate: Optional[np.ndarray | float] = None,
        source_h: Optional[np.ndarray] = None,
        source_hu: Optional[np.ndarray] = None,
        source_hv: Optional[np.ndarray] = None,
    ) -> float:
        st, cfg = self.state, self.cfg
        dt = float(np.clip(dt if dt is not None else self.cfl_dt(), cfg.min_dt, cfg.max_dt))
        rain = self._field(rain_rate, 0.0)
        infil = self._field(infiltration_rate, 0.0)
        net = rain - infil
        if source_h is not None:
            net = net + source_h
        dh, dhu, dhv = self._flux_divergence(st)
        h_new = np.where(self.valid, np.maximum(st.h + dt * (-dh + net), 0.0), 0.0)
        hu_new = st.hu + dt * (-dhu)
        hv_new = st.hv + dt * (-dhv)
        if source_hu is not None:
            hu_new = hu_new + dt * source_hu
        if source_hv is not None:
            hv_new = hv_new + dt * source_hv
        hu_new, hv_new = self._friction(h_new, hu_new, hv_new, dt)
        dry = (h_new <= cfg.h_dry) | ~self.valid
        st.h = h_new
        st.hu = np.where(dry, 0.0, hu_new)
        st.hv = np.where(dry, 0.0, hv_new)
        st.time += dt
        st.step += 1
        st.h_max = np.fmax(st.h_max if st.h_max is not None else h_new, h_new)
        return dt

    def run(
        self,
        duration_s: float,
        forcing: Any = None,
        callback: Optional[Callable] = None,
    ) -> SolverState:
        t_end = self.state.time + float(duration_s)
        n = 0
        while self.state.time < t_end - 1e-12 and n < self.cfg.max_steps:
            dt = min(self.cfl_dt(), t_end - self.state.time)
            rain = infil = 0.0
            src_h = src_hu = src_hv = None
            if forcing is not None:
                if hasattr(forcing, "rain_at"):
                    rain = forcing.rain_at(self.state.time, self.state)
                if hasattr(forcing, "infiltration_at"):
                    infil = forcing.infiltration_at(self.state.time, self.state)
                if hasattr(forcing, "fluvial_mass_source"):
                    src_h = forcing.fluvial_mass_source(self.state.time, self.state.h.shape)
                if hasattr(forcing, "momentum_source"):
                    src_hu, src_hv = forcing.momentum_source(self.state.time, self.state)
                if hasattr(forcing, "apply_boundary_depths"):
                    forcing.apply_boundary_depths(self.state)
            self.step(dt=dt, rain_rate=rain, infiltration_rate=infil,
                      source_h=src_h, source_hu=src_hu, source_hv=src_hv)
            n += 1
            if callback and n % self.cfg.record_every == 0:
                callback(self.state)
        if n >= self.cfg.max_steps:
            logger.warning("max_steps=%d at t=%.1fs", self.cfg.max_steps, self.state.time)
        return self.state

    def cfl_dt(self) -> float:
        """Adaptive Δt from peak |u|+c and terrain steepness."""
        st, cfg = self.state, self.cfg
        h = np.maximum(st.h, 0.0)
        u, v = st.velocity(cfg.h_dry)
        c = np.sqrt(G * h)
        spd = np.maximum(np.abs(u) + c, np.abs(v) + c)
        mx = float(np.nanmax(np.where(self.valid, spd, 0.0)))
        if mx < 1e-8:
            return cfg.max_dt
        dx = min(cfg.dx, cfg.dy)
        dt = cfg.cfl * dx / mx
        # Steep terrain → smaller step
        if self._max_slope > cfg.steepness_slope_threshold:
            dt *= cfg.steepness_cfl_factor
        return float(np.clip(dt, cfg.min_dt, cfg.max_dt))

    def _flux_divergence(self, st: SolverState):
        cfg = self.cfg
        h, hu, hv, z = st.h, st.hu, st.hv, st.z
        if self._use_numba:
            fx_h, fx_hu, fx_hv = _hll_x_numba(h, hu, hv, z, cfg.h_dry)
            fy_h, fy_hu, fy_hv = _hll_y_numba(h, hu, hv, z, cfg.h_dry)
        else:
            fx_h, fx_hu, fx_hv = _hll_x_numpy(h, hu, hv, z, cfg.h_dry)
            fy_h, fy_hu, fy_hv = _hll_y_numpy(h, hu, hv, z, cfg.h_dry)

        dh = np.zeros_like(h)
        dhu = np.zeros_like(h)
        dhv = np.zeros_like(h)
        dh[:, 1:-1] += (fx_h[:, 1:] - fx_h[:, :-1]) / cfg.dx
        dh[:, 0] += fx_h[:, 0] / cfg.dx
        dh[:, -1] -= fx_h[:, -1] / cfg.dx
        dh[1:-1, :] += (fy_h[1:, :] - fy_h[:-1, :]) / cfg.dy
        dh[0, :] += fy_h[0, :] / cfg.dy
        dh[-1, :] -= fy_h[-1, :] / cfg.dy

        dhu[:, 1:-1] += (fx_hu[:, 1:] - fx_hu[:, :-1]) / cfg.dx
        dhu[:, 0] += fx_hu[:, 0] / cfg.dx
        dhu[:, -1] -= fx_hu[:, -1] / cfg.dx
        dhu[1:-1, :] += (fy_hu[1:, :] - fy_hu[:-1, :]) / cfg.dy
        dhu[0, :] += fy_hu[0, :] / cfg.dy
        dhu[-1, :] -= fy_hu[-1, :] / cfg.dy

        dhv[:, 1:-1] += (fx_hv[:, 1:] - fx_hv[:, :-1]) / cfg.dx
        dhv[:, 0] += fx_hv[:, 0] / cfg.dx
        dhv[:, -1] -= fx_hv[:, -1] / cfg.dx
        dhv[1:-1, :] += (fy_hv[1:, :] - fy_hv[:-1, :]) / cfg.dy
        dhv[0, :] += fy_hv[0, :] / cfg.dy
        dhv[-1, :] -= fy_hv[-1, :] / cfg.dy

        zt = np.nan_to_num(z, nan=0.0)
        dhu = dhu + G * h * np.gradient(zt, cfg.dx, axis=1)
        dhv = dhv + G * h * np.gradient(zt, cfg.dy, axis=0)
        return dh, dhu, dhv

    def _friction(self, h, hu, hv, dt):
        n = self.n_manning
        hs = np.maximum(h, self.cfg.h_dry)
        u, v = hu / hs, hv / hs
        speed = np.sqrt(u * u + v * v)
        coef = G * n * n * speed / (hs ** (4.0 / 3.0) + 1e-12)
        fac = 1.0 / (1.0 + self.cfg.theta * dt * coef)
        return hu * fac, hv * fac

    def _field(self, val, default: float) -> np.ndarray:
        if val is None:
            return np.full((self.ny, self.nx), default)
        if np.isscalar(val):
            return np.full((self.ny, self.nx), float(val))
        a = np.asarray(val, dtype="float64")
        if a.shape != (self.ny, self.nx):
            raise ValueError(f"shape {a.shape} != {(self.ny, self.nx)}")
        return np.where(np.isfinite(a), a, 0.0)
