# Convenience targets. Everything runs from the project venv so I never mix
# this project's PyTorch with anything else on the machine.
#
# PY is the interpreter used to *create* the venv. SpeciesNet requires < 3.15,
# so I point at Anaconda's 3.12 rather than Homebrew's 3.14.
PY       ?= /opt/anaconda3/bin/python
VENV     := .venv
BIN      := $(VENV)/bin
CORRIDOR ?= lamar_valley
PHASE0   := $(BIN)/python scripts/phase0.py

.PHONY: setup setup-ml test coverage pull download detect sample report notebook

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

# ---- Phase 0, in order ----------------------------------------------------------
coverage:
	$(PHASE0) coverage

pull:
	$(PHASE0) pull --corridor $(CORRIDOR)

download:
	$(PHASE0) download --corridor $(CORRIDOR) --limit 400

detect:
	$(PHASE0) detect --corridor $(CORRIDOR)

sample:
	$(PHASE0) sample --corridor $(CORRIDOR) --n 30

report:
	$(PHASE0) report --corridor $(CORRIDOR) --write --json

notebook:
	$(BIN)/python -m jupyter lab notebooks/ 2>/dev/null || /opt/anaconda3/bin/jupyter lab notebooks/
