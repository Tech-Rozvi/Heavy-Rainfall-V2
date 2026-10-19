# Heavy-Rainfall-Model (full progressive build)

This archive includes the original science modules plus progressive upgrades:

- API streaming (CHIRPS, Copernicus DEM, ERA5/Open-Meteo)
- Zimbabwe AOI hardening (GAUL → Nominatim → province bbox fallbacks)
- Hydraulics (2D SWE, multi-peril, pipeline + GeoTIFF export)
- CMIP6 delta-change climate module
- EVT return periods
- CLI: `--mode api|local`, `--country/--adm1/--adm2/--adm3`, `--aoi`

## Quick start

```powershell
python -m pip install -r requirements.txt
python main.py --mode api --country Zimbabwe --adm1 Harare --start-date 2019-01-01 --end-date 2019-12-31
python main.py --mode api --aoi examples/harare_qa_small.geojson --start-date 2019-01-01 --end-date 2019-12-31
```

Synthetic data remains disabled unless `--allow-synthetic` is passed.
