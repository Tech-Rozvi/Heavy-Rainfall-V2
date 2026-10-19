#!/usr/bin/env python3
"""
Fetch real CHIRPS daily rainfall for an AOI and save as daily_precip.npy

Long periods are fetched year-by-year (ClimateSERV rejects multi-decade jobs).

Sources (verified open):
  - ClimateSERV CHIRPS API (AOI-mean time series) — primary
  - UCSB CHIRPS GeoTIFF daily tiles — spatial fallback

Examples:
  python scripts/fetch_chirps.py --point 31.05,-17.83 --buffer-km 25 \\
      --start 2000-01-01 --end 2023-12-31 --out data/raw/daily_precip_chirps.npy

  python scripts/fetch_chirps.py --bbox 30.8,-18.1,31.3,-17.6 \\
      --start 2010-01-01 --end 2020-12-31 --out data/raw/daily_precip_chirps.npy

Then run EPRF:
  python run_eprf.py --local-precip data/raw/daily_precip_chirps.npy --output-dir outputs/eprf_chirps
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch CHIRPS daily rainfall into .npy for ROZVI/EPRF")
    p.add_argument("--point", help="lon,lat")
    p.add_argument("--bbox", help="minx,miny,maxx,maxy")
    p.add_argument("--buffer-km", type=float, default=25.0)
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--out", default="data/raw/daily_precip_chirps.npy")
    p.add_argument("--meta-out", default=None, help="Optional JSON metadata path")
    args = p.parse_args()

    if args.point:
        lon, lat = [float(x) for x in args.point.replace(",", " ").split()]
        # ~1 deg ≈ 111 km
        d = args.buffer_km / 111.0
        bounds = (lon - d, lat - d, lon + d, lat + d)
    elif args.bbox:
        parts = [float(x) for x in args.bbox.replace(",", " ").split()]
        if len(parts) != 4:
            raise SystemExit("--bbox requires minx,miny,maxx,maxy")
        bounds = tuple(parts)
    else:
        raise SystemExit("Provide --point or --bbox")

    from src.data.streaming.remote_client import RemoteDataClient, StreamConfig

    client = RemoteDataClient(StreamConfig(request_timeout_s=120))
    print(f"Fetching CHIRPS for bounds={bounds} {args.start}→{args.end} ...")
    result = client.fetch_chirps_daily(bounds, args.start, args.end)
    precip = np.asarray(result["precipitation"], dtype="float32")
    if precip.ndim == 1:
        precip = precip.reshape(-1, 1, 1)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, precip)

    meta = {
        "bounds": bounds,
        "start": args.start,
        "end": args.end,
        "shape": list(precip.shape),
        "units": result.get("units", "mm/day"),
        "source": result.get("source"),
        "n_days": int(precip.shape[0]),
        "n_years_approx": round(precip.shape[0] / 365.25, 2),
        "crs": result.get("crs", "EPSG:4326"),
        "disclaimer": (
            "CHIRPS is a quasi-global rainfall product (Funk et al., Scientific Data). "
            "Use ≥20–30 years for stable extreme-value return levels."
        ),
    }
    meta_path = Path(args.meta_out) if args.meta_out else out.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out} shape={precip.shape}")
    print(f"Wrote {meta_path}")
    print(f"Source: {meta['source']}")
    print(f"Approx years: {meta['n_years_approx']}")
    if meta["n_years_approx"] < 20:
        print(
            "WARNING: Record shorter than ~20 years — GEV 100-year levels will be "
            "Very low confidence or NaN. Extend --start/--end."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
