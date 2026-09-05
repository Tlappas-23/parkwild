# Experiments

One entry per thing tried, with the number it produced, whether it was kept,
and why. Negative results are entries, not omissions. The point is that
nobody, including me in six weeks, re-runs something that already failed.

Format: date, what, number, kept?, why, where it lives.

## 2026-09-05

### E-001: Mapillary bbox tiling at 0.05 deg with `len(rows) < 2000` as "complete"
- **What:** first coverage pass over three corridors, trusting the documented 2000-row limit as a hard cap.
- **Number:** Lamar Valley 16,901 images; Moose-Wilson 7,080; Cades Cove crashed (HTTP 500).
- **Kept:** no.
- **Why:** a second pass with two extra splits gave 21,632 for Lamar. Direct test: tiles returning 1879, 1929, 1938, 1973 rows had quarters summing to 2559 to 3371; tiles at 1849 and below were complete. The cap is applied loosely.
- **Replaced by:** E-002. Code: `mapillary.CAP_SUSPECT_ROWS`; comparison test `tests/test_mapillary.py::test_v1_cap_rule_undercounts`.

### E-002: split tiles at >= 1500 rows and on HTTP 500
- **What:** treat >= 1500 rows as "probably capped" and quarter; treat a repeated 5xx on a splittable tile as "too heavy" and quarter.
- **Number:** Lamar 27,430 (101 tile queries), Moose-Wilson 24,231 (70), Cades Cove 39,410 (126); zero truncated leaves.
- **Kept:** yes. Cost: roughly 4x the requests on dense tiles.
- **Where:** `parkwild/mapillary.py`, ADR-0004.

### E-003: DuckDB `setseed()` + `random()` for a reproducible download sample
- **What:** seed the RNG and order by random() to pick 400 frames.
- **Number:** two consecutive calls returned different orders (test failure).
- **Kept:** no. Replaced by ordering on `hash(image_id || seed)`, stable across runs and machines.
- **Where:** `storage.images_pending_download`; `_v1` retained with a test that shows the instability is not present in v2.

### E-004: Overpass road length for Lamar Valley
- **What:** highway ways inside the corridor bbox, clipped by segment.
- **Number:** 58.7 km road, 75.9 km trail, 179 ways; density 467 images per road km.
- **Kept:** yes.
- **Failure on the way:** overpass-api.de answered HTTP 406 to python-requests' default User-Agent (three retries), kumi mirror 429. curl with any UA worked; requests with a named UA worked. Fix: named UA, lz4 mirror first.

### E-005: EXIF orientation on downloaded frames
- **What:** contact sheet of 12 random frames; 2 rendered upside down.
- **Number:** 13 of 400 frames carry orientation tag 3 (180 degrees), all from one contributor.
- **Kept:** SpeciesNet's loader applies `exif_transpose` (verified in source), so its boxes refer to the upright image; the review renderer now transposes too. Test with a synthetic tagged JPEG.

### E-006: Perspective-only Phase 0 sample
- **What:** exclude panoramas from the 400-frame sample.
- **Number:** 27,430 indexed; 23,740 (87%) are 4096 x 2048 spherical panoramas from one contributor in June 2024; 3,690 perspective frames from 5 contributors, 2014 to 2018.
- **Kept:** as one of two populations, not the only one (build spec). Slicing panoramas into 90-degree windows added; no result yet.
- **Expectation on record:** slicing fixes projection and framing, not resolution. At ~11 px per degree a bison at 100 m is ~11 px tall. Do not read slice results as extended range.

### E-007: Cluster count v1 (merge boxes within a frame)
- **What:** chain detections by (sequence, label, time, distance) at the box level.
- **Number:** on the fixture, two elk boxes in one frame collapsed to one cluster.
- **Kept:** no. Two boxes in one frame are two animals. v2 chains *frames* and counts the max boxes per frame within a chain.
- **Where:** `report.cluster_detections`; `_v1` retained with comparison test.

### E-008: GBIF for Yellowstone: what is actually in it
- **What:** facet GBIF occurrence counts by dataset inside the park bbox.
- **Number:** Mammalia 26,248 total, 25,292 iNaturalist mirror, 956 other. Aves 445,426 total, 421,940 eBird, 16,280 iNaturalist mirror, 7,206 other.
- **Kept:** skip the iNaturalist dataset by key (exact mirror); skip eBird (decision O-4 = skip: hotspot centroids, would be nine tenths of the data at the worst accuracy in it); ingest the rest.
- **Where:** ADR-0011, `gbif.INAT_DATASET_KEY`, `gbif.EBIRD_DATASET_KEY`.

### E-009: Quaternius license state
- **What:** confirm the license before downloading 3D assets.
- **Number:** pack page and OpenGameArt say CC0; site license page says QAL v1.0, updated 2026-08-28.
- **Kept:** proceed under QAL with credit (decision O-5). License page archived on Wayback and hashed; see docs/3d-assets.md.

### E-010: SpeciesNet on symlinked inputs
- **What:** first determinism run pointed SpeciesNet at a folder of symlinks to the downloaded frames.
- **Number:** zero predictions, a crash-shaped log (leaked semaphores, module dump), exit 1. The same three frames as real copies ran fine on MPS and CPU with identical output.
- **Kept:** no. `determinism_check.py` copies files. Not chased further: copies are cheap.

### E-011: SpeciesNet MPS vs CPU on three frames
- **What:** same three perspective frames, MPS then CPU.
- **Number:** identical labels and detection confidences to three decimals on all three. Labels were "blank" and "no cv result"; the meaning of the latter is an open question in speciesnet_runner.py.
- **Kept:** MPS provisionally; the 20-frame check (Q-1) decides.

### E-012: SpeciesNet backend on the M2 Pro (decision 1's condition)
- **What:** 20 perspective frames, same command, three backends/modes.
- **Number:** MPS batch 8: segfault (exit 139) at "Classifier preprocess 10/20" inside speciesnet/multiprocessing.py. MPS batch 1: abort (exit 134), same place. MPS `--run_mode multi_process`: hung past 10 minutes, killed. CPU batch 8: exit 0, 20 predictions.
- **Kept:** CPU is the backend. `phase0.py detect --backend cpu` is the default and `runs.backend` records it. MPS stays reachable via `--backend auto` for a future torch/speciesnet version.
- **Why it matters:** decision 1 predicted "silently wrong output rather than failing"; what happened was loud failure, which is the better outcome. The three-frame agreement (E-011) says MPS arithmetic was fine when it ran.
- **Where:** ADR-0012; reports/determinism.json holds the CPU run-to-run comparison.

### E-013: CPU run-to-run determinism, 20 frames
- **What:** the same 20 perspective frames scored twice on CPU (`scripts/determinism_check.py`), plus one MPS attempt with a 15-minute cap.
- **Number:** CPU run 1 vs run 2: byte-identical JSON = True, label mismatches 0, box-count mismatches 0, max score diff 0.0, max box diff 0.0. Timing 29.5 s and 29.6 s. MPS: failed: speciesnet failed (mps, exit -6).
- **Kept:** CPU, deterministic = True. No error bar needed for backend nondeterminism.
- **Where:** reports/determinism.json.

### E-014: first SpeciesNet pass over 400 Lamar perspective frames (CPU, v4.0.3a, country USA, admin1 WY)
- **What:** whole-frame inference on the pinned 400-frame sample (reports/samples/lamar_valley_perspective_download.json).
- **Number (pre-review, from the raw JSON):** frames with an animal box >= 0.1: 67 (16.8%); >= 0.2: 33 (8.2%); >= 0.5: 12 (3.0%); >= 0.8: 1 (0.2%). 43 animal boxes >= 0.2: 28 in 0.2 to 0.5, 14 in 0.5 to 0.8, 1 at 0.8+. Median box height 2.2% of the frame (about 60 px), p90 24.6%. Vehicle boxes in 189 frames (47%), human in 20. Zero model failures.
- **Ensemble labels on the 33 frames:** "unknown" 15, vehicle 5, american bison 5, human 3, animal 2, blank 2, domestic cattle 1.
- **Read:** the hit rate at 0.2 clears the spec's 5% line for a primary source; whether the boxes are animals is what the stratified review decides. The high band has one box, so the review cannot say anything about precision above 0.8 on this population. "domestic cattle" in Lamar Valley is almost certainly a bison the classifier could not separate at 60 px.
- **Kept:** as the perspective baseline. Timing: about 10 minutes on CPU for 400 originals.
- **Where:** data/predictions/lamar_valley_perspective.json; `runs` table once parsed.

### E-015: GBIF ingest, filter-after-fetch
- **What:** first Yellowstone GBIF ingest fetched every record in the bbox and dropped the skipped datasets client-side.
- **Number:** 26,248 mammal records downloaded to keep 956; GBIF deep paging ran at about one 300-row page per minute past offset ~10,000. Aves would have been 445,426 records for ~7,200 kept, roughly a day. Killed at mammals 24,000/26,248 after 85 minutes.
- **Kept:** no. Query wanted datasets by key (facet minus skip list, repeated `datasetKey=`); offsets stay small and pages stay fast.
- **Where:** `gbif.wanted_datasets`, `sightings.ingest_gbif`.

### E-016: SpeciesNet resume refused after a path-form change
- **What:** `phase0.py detect` re-invoked SpeciesNet on the 400 frames whose JSON already existed (from the direct CPU run), expecting the documented resume.
- **Number:** exit 1, "Filepath from loaded predictions is missing from the set of instances"; zero re-inference, results parsed anyway.
- **Why:** the direct run passed `data/images/lamar_valley`, the CLI passed the absolute path; resume compares strings.
- **Kept:** fix. All paths repo-relative with cwd=ROOT. The run row for the perspective population carries exit_code 1 for this reason; its predictions are the direct CPU run's.

### E-017: cells.geojson size
- **What:** first export emitted one feature per (cell, species) with a 12-month histogram each.
- **Number:** 17,653 features over 5,241 cells, 10.9 MB raw, 2.0 MB gzipped. Too slow for the 3-second phone budget.
- **Kept:** no. One feature per cell, species index on the collection, array entries, five-decimal coordinates: 2.16 MB raw, 365 KB gzipped, same information minus per-cell months (species.json keeps months per species).

### E-018: SpeciesNet on sliced panoramas (100 panoramas, 400 slices, CPU)
- **What:** the second Phase 0 population (ADR-0006): 90-degree horizon windows at yaw 0/90/180/270.
- **Number:** 64 of 400 slices with an animal box >= 0.2 (16%); 54 of 100 panoramas (54%). Stratified review of 17 boxes (10 low band, 7 mid, none above 0.8): 2 true positives, 14 false positives, 1 unsure. Precision 2/16 = 12% (95% CI 3 to 36%).
- **What the false positives were:** 7 the camera's own mounting arm (a black curved bar in every yaw090 slice from this contributor, and every box in the 0.5 to 0.8 band), 3 rocks, 2 clouds, 1 lone tree, 1 car. The two true positives: a bison running past parked cars at ~40 m (ensemble said vehicle) and a distant herd at ~250 m, about 8 px each (ensemble said blank).
- **Read:** the 54% "hit rate" is an artifact of the rig; strip the yaw090 rig region (or that contributor) and the population is closer to the perspective one. Q-2 (slices vs whole) stands unanswered; the rig must be masked first or the comparison measures the rig.
- **Kept:** as a documented negative result for panoramas as processed. Fix is cheap (mask a fixed region per contributor) and goes in Phase 2 only if Track B is routed anywhere.

### E-019: the "anything iNaturalist obscures" rule, first version
- **What:** coarsen any species with at least one taxon-obscured iNaturalist observation in the park.
- **Number:** 16,371 sightings coarsened, including bison (2 flagged of 7,822), black bear (72 of 2,210), coyote, marmot, mountain bluebird, moose and European starling. The species page showed "sensitive species" on a third of the grid.
- **Kept:** no. Majority rule (share >= 0.5): grizzly 99%, wolf 99%, bighorn 89%, river otter 100%, great grey owl 100% stay coarsened; everything under 5% is mapped normally. Nothing sits between 13% and 85%.
- **Also found:** GBIF and iNaturalist spell the same animal differently (Bos bison / Bison bison; Cervus elaphus / canadensis) and subspecies rows split counts. Names are normalised at export (config/taxonomy.toml); bison is one species with one count.

### E-020: the test suite wrote into the real decision ledger
- **What:** `log_filter` resolved its output path at import time, so every pytest and smoke run appended its six-row fixture filters to reports/decision_log.jsonl.
- **Number:** dozens of entries with corridor "test" or n_in under 20 among the real ones; found when a stash conflict showed bias and review entries timestamped at a test run.
- **Kept:** no. Path resolves at call time from PARKWILD_DECISION_LOG; conftest and smoke.py set it to a temp file; the ledger was scrubbed of entries with corridor "test" or fixture-sized inputs.

## Open questions with a planned experiment

- **Q-1 SpeciesNet determinism.** Answered (E-013).
- **Q-2 Panorama slices vs whole panoramas.** Ablation: same 100 panoramas whole and sliced; compare animal-box rate and review precision.
- **Q-3 Country filter on/off.** Same frames with and without `--country USA`; count label changes.
- **Q-4 Mapillary's own `animal--ground-animal` tags as a pre-filter.** Fetch with `pull --with-mapillary-detections`; overlap with MegaDetector boxes >= 0.2.
- **Q-5 Trivial baseline.** Predict the most common reviewed species for every true positive; compare with SpeciesNet's species agreement.
