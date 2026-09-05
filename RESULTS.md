# RESULTS

The honest ledger for this project. Every accuracy number lives here, including
the bad ones. Blocks between `<!-- phase0:...:start/end -->` markers are written
by `scripts/phase0.py report --write`; everything else is written by hand.

## Status

Phases follow BUILD_SPEC.md (three tracks; Phase 0 routes, it does not gate).

| Phase | State | Verified |
|---|---|---|
| 0. Feasibility (routing) | **steps 1 to 3 done for perspective frames; panorama slicing built; detection pending** | live coverage, index, 400-frame download, Overpass; offline tests + smoke |
| 1. Track A reference data | **built; Yellowstone ingest in progress** | live iNaturalist place lookup and GBIF counts; fixture tests |
| 2. Track B at scale | not started (waits on routing) | |
| 3. Dedup, validation, bias | cluster counting built for Phase 0; rest not started | |
| 4. Positions and export | Track A export built (cells.geojson, species.json, parquet, manifest) | fixture tests |
| 5. Application | not started | |
| 6. 3D layer | not started (model sourcing is a long-lead item) | |
| 7. Ship | not started | |

Done: token works, coverage measured, Lamar Valley indexed (27,430 images),
400 frames downloaded. Blocked on: an OK to run `make setup-ml` (PyTorch +
SpeciesNet, several GB), or the Kaggle alternative (run SpeciesNet there, copy
the JSON back, `phase0.py detect --parse-only`).

## Phase 0: feasibility (routing)

The question: what fraction of street-level frames in a wildlife corridor
contain a detectable animal, and are the detections real? Two populations are
measured and reported separately: whole perspective frames, and panoramas
sliced into four 90-degree horizon windows. Slicing fixes projection and
framing; it does not add resolution.

Routing rule from the build spec, applied per population:

| Outcome | Track B becomes |
|---|---|
| Precision >= 60% and hit rate >= 5% | primary data source; full crawl in Phase 2 |
| Precision 35 to 60%, or hit rate 2 to 5% | supplementary layer, best-coverage corridors only, visually distinct in the UI |
| Below that | documented negative result; app ships on Track A |

Ambiguous between bands: stop and ask. Recall is never reported.

### Corridor chosen: Lamar Valley

Coverage check run 2026-09-05 (`data/coverage_20260905.json`). All three
candidates have far more imagery than Phase 0 needs, so I took the brief's
first choice. Lamar is also the best case for detection range: open valley,
large animals, long sightlines. If it fails here it fails everywhere.

| Corridor | Images | Sequences | Captured | Bbox (km) |
|---|---|---|---|---|
| Lamar Valley, Yellowstone | 27,430 | 55 | 2014-09 to 2024-08 | 25 x 12 |
| Moose-Wilson Road, Grand Teton | 24,231 | 88 | 2014-08 to 2024-06 | 11 x 11 |
| Cades Cove Loop, Great Smokies | 39,410 | 123 | 2016-03 to 2026-06 | 10 x 7 |

Two crawler facts learned the hard way, now handled in code and documented in
the README: Mapillary's 2000-row cap is applied loosely (tiles at 1879+ rows
were truncated), and tiles with too many images return HTTP 500 rather than a
truncated list. The first coverage pass under-counted Lamar by a third.

**The Lamar index is 87% panoramas.** Of 27,430 images, 23,740 are 4096 x 2048
spherical panoramas from a single contributor in June to August 2024. The
3,690 perspective frames come from five contributors between 2014 and 2018
at 3264 x 2448 to 4032 x 3024. This matters twice over:

- Phase 0's sample follows the brief and uses perspective frames, so it measures
  the 2014 to 2018 population, not the 2024 one.
- A 4096-wide equirectangular covers 360 degrees, about 11 px per degree. A bison
  at 100 m is about 11 px tall in it. Whole-image detection on panoramas will
  find little; slicing them into 90-degree windows helps some but the pixels are
  not there. That is a Phase 2 experiment, not a Phase 0 one, and it is noted
  here so it does not get forgotten.

### Sample downloaded (2026-09-05)

400 perspective frames at original resolution, average 3789 x 2843 px, 749 MB,
zero download failures. Spread: 6 contributors, at most 20 frames per sequence,
years 2014 (40), 2015 (27), 2016 (186), 2018 (128), 2024 (19). Panoramas
excluded on purpose (see above).

### The five numbers

| # | Question | Perspective frames | Sliced panoramas |
|---|---|---|---|
| 1 | Fraction of images with any MegaDetector animal detection >= 0.2, with distinct-cluster count | _not run_ | _not run_ |
| 2 | Of those, fraction that are real animals on stratified manual inspection (~30 boxes), with 95% interval | _not run_ | _not run_ |
| 3 | Distance of true positives from the camera; range beyond which detection fails | _not run_ | _not run_ |
| 4 | Species-level agreement with my own eyes on the true positives | _not run_ | _not run_ |
| 5 | Mapillary density in the corridor (images per km) and date range | 27,430 images over 59 km of road (OSM): **467 per road km**. Captured 2014-09 to 2024-08, but 87% are June 2024 panoramas from one contributor; the 3,690 perspective frames run 2014 to 2018 plus a few in 2024. |

### Routing decision

_Pending detection. Track A proceeds regardless (BUILD_SPEC.md). The decision
and the numbers behind it go to DECISIONS.md when made._

### Auto-generated numbers

The block below is (re)written by `make report`. Hand-edit nothing inside the markers.

<!-- phase0:lamar_valley:perspective:start -->
_not yet run_
<!-- phase0:lamar_valley:perspective:end -->

<!-- phase0:lamar_valley:pano:start -->
_not yet run_
<!-- phase0:lamar_valley:pano:end -->

## Phase 1: Track A reference data

Yellowstone first (iNaturalist place 10211; GBIF by the park's bbox).

GBIF counts measured 2026-09-05 for the Yellowstone bbox, human and machine
observations with coordinates:

| Class | Total | iNaturalist mirror | eBird | Other datasets |
|---|---|---|---|---|
| Mammalia | 26,248 | 25,292 | 0 | 956 |
| Aves | 445,426 | 16,280 | 421,940 | 7,206 |

The iNaturalist mirror is skipped in GBIF (ingested directly instead). eBird
is not ingested until decided (DECISIONS.md ADR-0011): 421,940 checklist
records would be nine tenths of the park's data and their coordinates are
checklist locations, not bird locations. Bird counts below therefore
understate what eBird knows.

### Yellowstone ingest

_In progress._

