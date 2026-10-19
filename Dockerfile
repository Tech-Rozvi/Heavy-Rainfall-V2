# ROZVI reproducible runtime (Phase 11)
# Build:  docker build -t rozvi:0.10.0 .
# Verify: docker run --rm rozvi:0.10.0 bash scripts/verify.sh
# API:    docker run --rm -p 8000:8000 rozvi:0.10.0 uvicorn api.app:app --host 0.0.0.0 --port 8000

FROM python:3.11-slim-bookworm

LABEL org.opencontainers.image.title="ROZVI" \
      org.opencontainers.image.description="Climate / extreme precipitation / flood-forcing intelligence" \
      org.opencontainers.image.version="0.10.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System libraries commonly required by geospatial wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gdal-bin \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
        proj-data \
        proj-bin \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
# Core scientific stack first; full requirements may fail on optional cloud clients
RUN pip install --no-cache-dir \
        "numpy>=1.26" "scipy>=1.11" "pyyaml>=6.0" \
        "fastapi>=0.100" "uvicorn>=0.23" "httpx>=0.24" \
        "rasterio>=1.3" "shapely>=2.0" "pyproj>=3.5" \
        "scikit-learn>=1.3" "matplotlib>=3.7" "pytest>=7.4" \
    && pip install --no-cache-dir -r requirements.txt || true

COPY . /app

# Default: print platform version (override with verify or uvicorn)
CMD ["python", "-c", "from src.rozvi import __platform_name__, __version__; print(__platform_name__, __version__)"]
