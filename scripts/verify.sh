#!/usr/bin/env bash
# One-command scientific verification for ROZVI (Phase 9)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "=== ROZVI verify ==="
python -c "from src.rozvi import __version__, __platform_name__; print(__platform_name__, __version__)"

echo "=== Unit tests ==="
python -m pytest tests/rozvi tests/hydrology tests/hydraulics tests/risk tests/eprf -q --tb=line

echo "=== Phase 8 end-to-end demo ==="
python examples/workflow_phase8_end_to_end.py

echo "=== API handlers ==="
python -c "from src.rozvi.api_handlers import info, capabilities; print(info()['version']); print(capabilities()['capabilities']['flood_depth'])"

echo "=== VERIFY OK ==="
