# Phase 11 — Reproducible runtime packaging

**Platform:** ROZVI **0.10.0**

## Deliverables

| Item | Path |
|------|------|
| Dockerfile | `Dockerfile` |
| Docker ignore | `.dockerignore` |
| Compose (API) | `docker-compose.yml` |
| Makefile | `Makefile` |
| Reproducibility guide | `docs/REPRODUCIBILITY.md` |

## Design choices

- **Slim Python 3.11** base with GDAL/GEOS/PROJ system libs for geospatial wheels.
- Core pip packages installed explicitly before full `requirements.txt` so image builds remain useful if optional cloud deps fail.
- Default container CMD only prints the platform version (no silent heavy jobs).
- No claim that Docker equals scientific validation.

## Tests

`tests/rozvi/test_phase11_packaging.py` — presence and content checks only
(Docker daemon not required in CI).

## Version

ROZVI **0.10.0**
