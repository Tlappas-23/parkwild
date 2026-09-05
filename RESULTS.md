# RESULTS

The honest ledger for this project. Every accuracy number lives here, including
the bad ones. Blocks between `<!-- phase0:...:start/end -->` markers are written
by `scripts/phase0.py report --write`; everything else is written by hand.

## Status

| Phase | State | Verified |
|---|---|---|
| 0. Feasibility gate | **code written, not yet run** | offline unit tests only (`make test`) |
| 1. Ingest | not started | |
| 2. Detection | not started | |
| 3. Position estimation | not started | |
| 4. Validation | not started | |
| 5. Output | not started | |

Blocked on: a Mapillary client token in `.env`, and an OK to run `make setup-ml`
(PyTorch + SpeciesNet, several GB).

## Phase 0: feasibility gate

The question: what fraction of street-level frames in a wildlife corridor
contain a detectable animal, and are the detections real?

Stop rule from the brief: if the true-positive rate is under ~2% of frames, or
the boxes are mostly vegetation, say so and stop.

### Corridor chosen

_Not yet chosen. `phase0.py coverage` reports image counts for Lamar Valley,
Moose-Wilson Road and Cades Cove; the first with real coverage wins._

### The five numbers

| # | Question | Answer |
|---|---|---|
| 1 | Fraction of images with any MegaDetector animal detection >= 0.2 | _not run_ |
| 2 | Of those, fraction that are real animals on manual inspection (~30 samples) | _not run_ |
| 3 | Distance of true positives from the camera; range beyond which detection fails | _not run_ |
| 4 | Species-level agreement with my own eyes on the true positives | _not run_ |
| 5 | Mapillary density in the corridor (images per km) and date range | _not run_ |

### Decision

_Pending. Do not start Phase 1 until this line says go._

### Auto-generated numbers

The block below is (re)written by `make report`. Hand-edit nothing inside the markers.

<!-- phase0:lamar_valley:start -->
_not yet run_
<!-- phase0:lamar_valley:end -->
