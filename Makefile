# ROZVI developer targets (Phase 11)
PYTHON ?= python
export PYTHONPATH := $(CURDIR)$(if $(PYTHONPATH),:$(PYTHONPATH),)

.PHONY: help version test verify demo api docker-build docker-verify

help:
	@echo "ROZVI targets: version test verify demo api docker-build docker-verify"

version:
	@$(PYTHON) -c "from src.rozvi import __platform_name__, __version__, __eprf_version__; print(f'{__platform_name__} {__version__} (EPRF {__eprf_version__})')"

test:
	$(PYTHON) -m pytest tests/rozvi tests/api tests/hydrology tests/hydraulics tests/risk -q --tb=line

verify:
	bash scripts/verify.sh

demo:
	$(PYTHON) examples/workflow_phase8_end_to_end.py

api:
	uvicorn api.app:app --host 0.0.0.0 --port 8000

docker-build:
	docker build -t rozvi:0.10.0 .

docker-verify:
	docker run --rm rozvi:0.10.0 bash scripts/verify.sh
