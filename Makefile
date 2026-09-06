# Convenience targets. Everything runs from the project venv so I never mix
# this project's PyTorch with anything else on the machine.
#
# PY is the interpreter used to *create* the venv. SpeciesNet requires < 3.15,
# so I point at Anaconda's 3.12 rather than Homebrew's 3.14.
PY       ?= /opt/anaconda3/bin/python
VENV     := .venv
BIN      := $(VENV)/bin
CORRIDOR ?= lamar_valley
POPULATION ?= perspective
BACKEND ?= cpu
PARK ?= yellowstone
TRACKA := $(BIN)/python scripts/track_a.py
PHASE0   := $(BIN)/python scripts/phase0.py

.PHONY: setup setup-ml test lint secrets hooks protect ship coverage pull download slice detect sample report notebook track-a track-b export bias smoke app app-data

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip

## light install: crawler, DuckDB, tests, notebook kernel. No PyTorch.
setup: $(BIN)/python
	$(BIN)/pip install -q -r requirements.txt
	$(BIN)/pip install -q -e .
	$(BIN)/python -m ipykernel install --user --name parkwild --display-name "parkwild (.venv)"

## heavy install: PyTorch + yolov5 + SpeciesNet (several GB, plus ~1 GB of weights on first run).
setup-ml: $(BIN)/python
	$(BIN)/pip install -r requirements-ml.txt
	$(BIN)/python -c "import torch, speciesnet; print('torch', torch.__version__, '| mps:', torch.backends.mps.is_available())"

test:
	$(BIN)/python -m pytest -q

lint:
	$(BIN)/ruff check src tests scripts
	$(BIN)/python scripts/provenance_report.py --strict

## Track B -> sightings (after detect): make track-b
track-b:
	$(BIN)/python scripts/track_b.py sightings --corridor $(CORRIDOR) --park $(PARK) --population $(POPULATION)

## the app: install, build, enforce the JS budget
app:
	cd app && npm install --no-audit --no-fund && npm run build && npm run budget

## copy the baked exports into the app's public data folder
app-data:
	mkdir -p app/public/data/$(PARK) && cp data/export/$(PARK)/*.{geojson,json} app/public/data/$(PARK)/

## secret scan over everything git tracks (CI runs the same)
secrets:
	$(BIN)/python scripts/check_secrets.py --tree

## install the pre-commit secret guard for this clone
hooks:
	git config core.hooksPath .githooks
	@echo "pre-commit secret scan installed"

## land the working tree on main via PR + CI (main refuses direct pushes)
ship:
	scripts/ship.sh "$(TITLE)" $(BODY)

## lock main on GitHub: make protect REPO=owner/name
protect:
	scripts/github_protect.sh $(REPO)

# ---- Phase 0, in order ----------------------------------------------------------
coverage:
	$(PHASE0) coverage

pull:
	$(PHASE0) pull --corridor $(CORRIDOR)

download:
	$(PHASE0) download --corridor $(CORRIDOR) --limit 400

slice:
	$(PHASE0) slice --corridor $(CORRIDOR)

detect:
	$(PHASE0) detect --corridor $(CORRIDOR) --population $(POPULATION) --backend $(BACKEND)

sample:
	$(PHASE0) sample --corridor $(CORRIDOR) --population $(POPULATION) --n 30

report:
	$(PHASE0) report --corridor $(CORRIDOR) --population $(POPULATION) --write --json

# ---- Track A: reference sightings ---------------------------------------------
track-a:
	$(TRACKA) all --park $(PARK)

export:
	$(TRACKA) export --park $(PARK)

bias:
	$(TRACKA) bias --park $(PARK) --corridor $(CORRIDOR) --write

## end-to-end on fixtures, no network; CI runs this with a 5 minute cap
smoke:
	$(BIN)/python scripts/smoke.py

notebook:
	$(BIN)/python -m jupyter lab notebooks/ 2>/dev/null || /opt/anaconda3/bin/jupyter lab notebooks/
