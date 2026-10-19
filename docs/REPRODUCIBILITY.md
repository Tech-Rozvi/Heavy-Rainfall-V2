# Reproducibility guide (ROZVI 0.10.0)

## Local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=$PWD
make version
make test
make verify
```

## Docker

```bash
docker build -t rozvi:0.10.0 .
docker run --rm rozvi:0.10.0          # prints platform version
docker run --rm rozvi:0.10.0 bash scripts/verify.sh
docker compose up --build             # API on :8000
```

The image installs a **core** scientific stack first, then attempts the full
`requirements.txt`. Optional cloud clients (s3fs, planetary-computer, etc.)
may be absent in constrained build environments; core EVT, hydrology, chain,
and API handlers do not require them.

## What is reproducible here

| Artefact | How |
|----------|-----|
| Unit tests | `make test` / `scripts/verify.sh` |
| Phase 8 demo | synthetic AMS + toy DEM (deterministic seed) |
| API handlers | `src/rozvi/api_handlers.py` (no network) |

## What is **not** fully reproducible from this repo alone

| Artefact | Why |
|----------|-----|
| National gauge archives | External data agreements |
| Event-validated flood maps | Requires observed flood events not bundled |
| CMIP6/CORDEX fields | Registry only; data must be supplied |
| Full multi-source satellite fusion | Product alignment is caller responsibility |

## Provenance

Pipeline and chain outputs should write provenance JSON (`src.rozvi.provenance`,
`provenance_for_chain`). Prefer config from `config/rozvi.yaml`.
