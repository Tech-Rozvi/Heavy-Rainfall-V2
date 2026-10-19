# Heavy Rainfall Model v6

## Features
- API streaming (CHIRPS, DEM, ERA5/Open-Meteo)
- Multi-province AOI merge (Zimbabwe)
- Dynamic Manning n from ESA WorldCover; SCS CN from LC + SoilGrids HSG
- `--mode forecast` early warning (Open-Meteo QPF → 2D SWE)
- OSM building exposure counts (0.15 / 0.5 / 1.0 m)
- Executive HTML/JSON site hazard report (Jinja2)
- FastAPI Web UI at http://127.0.0.1:8000/

## Quick start
```bash
pip install -r requirements.txt
python main.py --mode api --country Zimbabwe --adm1 "Harare,Bulawayo" --start-date 2019-01-01 --end-date 2019-12-31
python main.py --mode forecast --country Zimbabwe --adm1 Harare --forecast-days 5 --start-date 2019-01-01 --end-date 2019-01-02
uvicorn api.app:app --host 0.0.0.0 --port 8000
```
