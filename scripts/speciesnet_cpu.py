#!/usr/bin/env python
"""
Run SpeciesNet with the Apple MPS backend hidden, so PyTorch falls back to CPU.

SpeciesNet has no device flag; it asks torch whether MPS is available at model
load. Decision 1 (2026-09-05) says: try MPS, but any misbehaviour means force
CPU and record the backend. This wrapper is that switch.

FIRST ATTEMPT: replace `torch.backends.mps.is_available` itself. Broke torch,
which reaches for `.__wrapped__` on that function. CURRENT: replace the C
binding underneath it, `torch._C._mps_is_available`, and leave the Python
wrapper intact. Usage is identical to `python -m speciesnet.scripts.run_model`.
"""
import runpy
import sys

import torch

torch._C._mps_is_available = lambda: False  # type: ignore[attr-defined]
assert not torch.backends.mps.is_available(), "MPS still reported available; wrapper is ineffective"
sys.argv[0] = "speciesnet.scripts.run_model"
runpy.run_module("speciesnet.scripts.run_model", run_name="__main__", alter_sys=True)
