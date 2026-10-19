#!/usr/bin/env python3
"""
EPRF v8.1 CLI — Extreme Precipitation Risk Framework

Examples
--------
# Run on bundled synthetic daily precipitation (for testing only)
python run_eprf.py --config config/eprf/eprf_config.yaml --local-precip data/raw/daily_precip.npy

# Production path (user-supplied NetCDF / Zarr)
python run_eprf.py --config config/eprf/eprf_config.yaml --precip-path /data/chirps_daily.nc --varname precip
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# Ensure package root is importable
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils import load_config, get_logger
from src.eprf.pipeline import run_eprf

logger = get_logger("run_eprf")


def main():
    parser = argparse.ArgumentParser(description="EPRF v8.1 Extreme Precipitation Risk Framework")
    parser.add_argument("--config", default="config/eprf/eprf_config.yaml")
    parser.add_argument("--local-precip", default=None, help="Path to .npy daily precip (T,Y,X)")
    parser.add_argument("--precip-path", default=None, help="Path to NetCDF/Zarr (future)")
    parser.add_argument("--varname", default="precip")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--allow-synthetic", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    out_dir = Path(args.output_dir or cfg.get("paths", {}).get("output_dir", "outputs/eprf"))

    if args.local_precip:
        daily = np.load(args.local_precip)
        logger.info("Loaded local precip %s shape=%s", args.local_precip, daily.shape)
    elif args.allow_synthetic or cfg.get("data_acquisition", {}).get("allow_synthetic"):
        path = ROOT / "data" / "raw" / "daily_precip.npy"
        daily = np.load(path)
        logger.warning("Using bundled synthetic precipitation — results are NOT real-world calibrated.")
    else:
        logger.error("No precipitation source provided. Use --local-precip or --allow-synthetic for tests.")
        sys.exit(1)

    result = run_eprf(daily, cfg, output_dir=out_dir)
    print("\n=== EPRF v8.1 Summary ===")
    s = result["summary"]
    print(f"Mean annual precip (domain): {s['map_mm_mean']:.1f} mm")
    print(f"Mean Rx1day (domain):        {s['rx1day_mean']:.1f} mm")
    def _fmt(v):
        try:
            import math
            return "nan" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.1f}"
        except Exception:
            return str(v)
    print(f"Mean 100-yr return level:    {_fmt(s['rl_100_mean'])} mm  "
          f"[{_fmt(s['rl_100_mean_lower'])}, {_fmt(s['rl_100_mean_upper'])}]")
    print(f"Confidence flags:            {s['confidence_counts']}")
    for note in s.get("notes") or []:
        print(f"NOTE: {note}")
    print(f"Outputs:                     {result['output_dir']}")
    print("\nScientific statement: Return levels are GEV quantiles of annual maxima "
          "with parametric bootstrap CIs. This is not a weather forecast.")


if __name__ == "__main__":
    main()
