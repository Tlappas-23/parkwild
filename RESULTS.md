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
| 2. Track B at scale | **in progress at supplementary scope**: all 3,690 Lamar perspective frames downloading, CPU inference next, then `track_b.py sightings` | ADR-0013/0014 |
| 3. Dedup, validation, bias | cluster counting built for Phase 0; rest not started | |
| 4. Positions and export | Track A export built (cells.geojson, species.json, parquet, manifest) | fixture tests |
| 5. Application | **skeleton live-tested locally**: map, species, detail, about on real data; deploys to GitHub Pages on merge | screenshots 2026-09-05 |
| 6. 3D layer | not started (model sourcing is a long-lead item) | |
| 7. Ship | Pages workflow + JS budget in CI; offline, Lighthouse, a11y pass not started | |

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

### Perspective frames: first read (reviewer: claude, 2026-09-05)

Stratified review of 20 boxes (10 / 9 / 1 per band; the top band has one
box in the whole population, so it cannot be judged). Verdicts are in
`data/review/lamar_valley/perspective/review_claude.csv`; a second pass by
the owner goes in `review.csv` under reviewer `me` and is reported separately.

- **Hit rate:** 33 of 400 frames have an animal box at 0.2, 8.2% (95% CI 6 to 11%).
- **Precision:** 42% (95% CI 23 to 64%, n=19). By band: 0.2 to 0.5 33% (95% CI 12 to 65%, n=9); 0.5 to 0.8 44% (95% CI 19 to 73%, n=9); 0.8+ 100% (95% CI 21 to 100%, n=1).
- **What the false positives were:** 6 people (3 groups of hikers, 2 motorcyclists), 4 lone conifers on hillsides, 1 car, 1 patch of road. The ensemble labels all six people "human", so a filter on the ensemble label would remove them; the trees are the residual problem, and the highest-confidence false positive (0.737) is a tree.
- **Range:** confirmed bison at 45 to 150 m. The two farthest (130 and 150 m) scored 0.20 and 0.26, at the threshold. Nothing beyond 150 m was detected at all; that is the practical range for a bison-sized animal in a ~3800 px frame.
- **Species:** all 8 true positives are bison. The ensemble said "american bison" for 5 (62%), "vehicle" for 2 and "domestic cattle" for 1. The trivial baseline ("say bison") scores 8 of 8. In Lamar Valley the classifier adds nothing over the detector; that may not hold for a corridor with several species.
- **Recall:** unmeasured.

**Routing read (perspective):** hit rate clears the primary line (>= 5%);
precision sits in the supplementary band (35 to 60%) with an interval that
touches both neighbours because n is 19. Per the spec that is a stop-and-ask.

### Sliced panoramas: first read (reviewer: claude, 2026-09-05)

100 panoramas from the dominant 2024 contributor, 400 slices. Stratified
review of 17 boxes (10 low band, 7 mid band, none above 0.8).

- **Hit rate:** 54 of 100 panoramas (16% of slices) have a box at 0.2. **Artifact.** Seven of the seventeen sampled boxes, and every box in the 0.5 to 0.8 band, are the panorama camera's own mounting arm, a black curved bar present in every right-facing (yaw090) slice.
- **Precision:** 2 of 16 judged, 12% (95% CI 3 to 36%). The other false positives: 3 rocks, 2 clouds, 1 lone tree, 1 car.
- **True positives:** a bison running past parked cars at ~40 m (ensemble: vehicle) and a herd on pasture at ~250 m, about 8 px per animal (ensemble: blank). Both are bison.
- **Read:** panoramas as processed are a negative result, and not because of resolution alone: the rig sits in a fixed place in the frame and a mask would remove the mid band's junk entirely. With the rig masked, the low band is rocks and clouds, and the model could not name either bison. Slicing did not extend range; nothing was found past ~250 m and that one is at the edge of a guess.
- **Recall:** unmeasured.

### Routing decision

**Supplementary layer for perspective frames; panoramas excluded until the
camera rig is masked and re-measured.** Confirmed by the owner 2026-09-05
(ADR-0013). Phase 2 runs at that scope on Lamar Valley.

### Auto-generated numbers

The blocks below are (re)written by `make report POPULATION=...`. Hand-edit
nothing inside the markers.

#### Perspective frames, reviewer claude

<!-- phase0:lamar_valley:perspective:claude:start -->
_Population: **perspective**. Generated 2026-09-05 15:05 from `data/parkwild.duckdb`. Model versions: 4.0.3a. Recall: **unmeasured**._

**Volume**

| Indexed (this population) | Downloaded | Download failed | Run through SpeciesNet | Frames/slices scored | Model failures |
|---|---|---|---|---|---|
| 3,690 | 400 | 0 | 400 | 400 | 0 |

**1. Images with any MegaDetector animal detection**

| Threshold | Images | Fraction |
|---|---|---|
| >= 0.2 | 33 | 8.2% (95% CI 6 to 11%) |
| >= 0.5 | 12 | 3.0% (95% CI 2 to 5%) |
| >= 0.8 | 1 | 0.2% (95% CI 0 to 1%) |

At >= 0.2: 43 animal boxes in 33 images form 25 frame-chains (same sequence, same label, consecutive frames within 60 s and 200 m), an estimated 34 distinct individuals; duplicate rate 20.9%.
For context at >= 0.2: 20 images have a human box and 189 a vehicle box.

Top ensemble labels on images with an animal box >= 0.2: unknown (15), vehicle (5), american bison (5), human (3), blank (2), animal (2), domestic cattle (1)

**2. True positives on manual inspection** (20 boxes reviewed, stratified by confidence band, reviewer claude)

- true positive: 8, false positive: 11, unsure: 1
- precision (tp / (tp + fp)): 42.1% (95% CI 23 to 64%)
- band 0.2-0.5: n=10, precision 33.3% (95% CI 12 to 65%)
- band 0.5-0.8: n=9, precision 44.4% (95% CI 19 to 73%)
- band 0.8-1.0: n=1, precision 100.0% (95% CI 21 to 100%)
- recall: unmeasured (no exhaustive annotation exists; a number would be invented)

**3. Distance of true positives from the camera** (n=8 with an estimate)

- median 70 m, p90 136 m, farthest confirmed 150 m

**4. Species agreement on true positives** (8 judged)

- exact: 5, correct coarser taxon (rollup): 0, wrong: 3
- trivial baseline (always say 'american bison'): 100.0% on n=8

**5. Mapillary density in the corridor** (whole corridor, both populations)

- 27,430 images in 55 sequences from 8 contributors; 23,740 panoramas
- road inside bbox (OSM): n/a; trail: n/a; images per road km: n/a
- captured between 2014-09-02 22:10:04 and 2024-08-15 22:04:02.856000
- this population by year: 2014: 376, 2015: 513, 2016: 1,263, 2018: 1,508, 2019: 1, 2024: 29
- this population by month: 3: 12, 6: 1, 7: 311, 8: 29, 9: 1,829, 10: 1,508
- camera types: spherical: 23,740, perspective: 3,690

<!-- phase0:lamar_valley:perspective:claude:end -->

#### Sliced panoramas, reviewer claude

<!-- phase0:lamar_valley:pano:claude:start -->
_Population: **pano**. Generated 2026-09-05 15:08 from `data/parkwild.duckdb`. Model versions: 4.0.3a. Recall: **unmeasured**._

**Volume**

| Indexed (this population) | Downloaded | Download failed | Run through SpeciesNet | Frames/slices scored | Model failures |
|---|---|---|---|---|---|
| 23,740 | 100 | 0 | 100 | 400 | 0 |

**1. Images with any MegaDetector animal detection**

| Threshold | Images | Fraction |
|---|---|---|
| >= 0.2 | 54 | 54.0% (95% CI 44 to 63%) |
| >= 0.5 | 8 | 8.0% (95% CI 4 to 15%) |
| >= 0.8 | 0 | 0.0% (95% CI 0 to 4%) |

At >= 0.2: 87 animal boxes in 54 images form 51 frame-chains (same sequence, same label, consecutive frames within 60 s and 200 m), an estimated 78 distinct individuals; duplicate rate 10.3%.
For context at >= 0.2: 6 images have a human box and 95 a vehicle box.

Top ensemble labels on images with an animal box >= 0.2: unknown (28), blank (26), animal (7), vehicle (3)

**2. True positives on manual inspection** (17 boxes reviewed, stratified by confidence band, reviewer claude)

- true positive: 2, false positive: 14, unsure: 1
- precision (tp / (tp + fp)): 12.5% (95% CI 3 to 36%)
- band 0.2-0.5: n=10, precision 22.2% (95% CI 6 to 55%)
- band 0.5-0.8: n=7, precision 0.0% (95% CI 0 to 35%)
- band 0.8-1.0: n=0, precision n/a
- recall: unmeasured (no exhaustive annotation exists; a number would be invented)

**3. Distance of true positives from the camera** (n=2 with an estimate)

- median 145 m, p90 229 m, farthest confirmed 250 m

**4. Species agreement on true positives** (2 judged)

- exact: 0, correct coarser taxon (rollup): 0, wrong: 2
- trivial baseline (always say 'american bison'): 100.0% on n=2

**5. Mapillary density in the corridor** (whole corridor, both populations)

- 27,430 images in 55 sequences from 8 contributors; 23,740 panoramas
- road inside bbox (OSM): n/a; trail: n/a; images per road km: n/a
- captured between 2014-09-02 22:10:04 and 2024-08-15 22:04:02.856000
- this population by year: 2024: 23,740
- this population by month: 6: 23,740
- camera types: spherical: 23,740, perspective: 3,690

<!-- phase0:lamar_valley:pano:claude:end -->

## Phase 2: Track B at supplementary scope

Scope from ADR-0013: Lamar Valley perspective frames only, all 3,690 of
them; detector confidence >= 0.5; ensemble labels human / vehicle / blank
dropped; one sighting per frame-chain; species named only at classifier
>= 0.8, otherwise "unidentified large mammal (model)"; camera position with
150 m as the stated accuracy (ADR-0014). Panoramas out until the rig is
masked.

_Numbers land here when the full-corridor inference finishes._

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

### Yellowstone ingest (2026-09-05)

| | |
|---|---|
| iNaturalist research-grade Mammalia + Aves | 51,643 observations (place 10211) |
| GBIF, other datasets, Mammalia | 956 of 26,248 in the bbox (25,292 were the iNaturalist mirror, never downloaded) |
| GBIF, other datasets, Aves | 7,206 of 445,426 (421,940 eBird and 16,280 mirror, never downloaded) |
| Total | 59,805 sightings; 31,802 mammals, 28,003 birds |
| Coordinates | 55,156 open, 4,649 obscured by the source (7.8%): counted, never mapped |
| Cross-source duplicates | 0 marked. With the iNaturalist mirror excluded by dataset key, the remaining GBIF datasets are independent programmes. |
| Suppression at export | 16 open-coordinate rows excluded (wolf, wolverine, lynx); the rest of those species were already obscured by iNaturalist |

Export: `cells.geojson` one feature per H3 r9 cell with a species index
(first version was 10.9 MB with geometry repeated per species, E-017),
`species.json`, `sightings.parquet` (59,805 rows), `bias.json`, `manifest.json`.

**Phase 1 acceptance: met.** A park's worth of real sightings is in DuckDB and
exported in the shape the app consumes; the app builds against it.

### Road and seasonal bias (Lamar Valley imagery vs Yellowstone sightings)

Measured by `track_a.py bias`; block below is auto-generated.

<!-- bias:lamar_valley:start -->
**Road bias** (lamar_valley imagery vs yellowstone sightings inside the corridor bbox, H3 r9, ring 1)

- 11,402 independent open-coordinate sightings in the bbox; 8,546 within imagery coverage
- **25% fall outside coverage** and are invisible to the imagery method by construction
- Aves: 4,696 sightings, 38% outside coverage
- Mammalia: 6,706 sightings, 16% outside coverage

**Seasonal bias**

| | J | F | M | A | M | J | J | A | S | O | N | D |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| imagery | 0 | 0 | 12 | 0 | 0 | 23,741 | 311 | 29 | 1,829 | 1,508 | 0 | 0 |
| sightings | 743 | 841 | 556 | 1,039 | 8,404 | 17,275 | 12,694 | 8,481 | 6,820 | 2,086 | 304 | 370 |

- June to August share: imagery 88%, sightings 64%
- months with no imagery at all: [1, 2, 4, 5, 11, 12]

<!-- bias:lamar_valley:end -->

**Reading:** a quarter of independent sightings inside the corridor are more
than ~350 m from any camera position, and birds far more so than mammals
(38% vs 16%). Imagery is 88% June, from one contributor; human sightings
peak May to August but exist in every month. Any Track B layer inherits both
biases and the About page says so with these numbers.
