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

### E-021: what the first live app got wrong, and the screenshot trap
- **What:** owner review of the deployed app.
- **Findings:** no photographs, monogram tiles, a busy basemap; the CSP meta tag blocked iNaturalist's image hosts once photos were added; MapLibre's container had zero height under its own stylesheet; a stale service-worker cache tripped the integrity check after a rebuild.
- **Also learned:** the browser extension's tab is a background tab (`document.visibilityState === "hidden"`), so the map's animation-frame loop is throttled and screenshots of the WebGL canvas come out grey even though the app is fine; image checks via script (`img.complete && naturalWidth > 0`) are the reliable test there.
- **Kept:** photographs everywhere (ADR-0015), OpenFreeMap positron basemap, CSP with both image hosts, a ResizeObserver on the map container, data URLs keyed by manifest hash, `preserveDrawingBuffer` for captures.

### E-022: full Lamar Valley perspective corridor
- **What:** all 3,690 perspective frames through SpeciesNet on CPU (about 55 minutes), then ADR-0014's filters.
- **Number:** 266 frames (7.2%) with an animal box at 0.2, 102 (2.8%) at 0.5; 3,510 animal boxes -> 110 after confidence and label filters -> 31 frame-chains -> 31 sightings: 3 named bison, 28 unidentified large mammals (two confident "domestic cattle" calls folded in; no cattle in Yellowstone).
- **Read:** the 400-frame sample's 8.2% at 0.2 was slightly high; the corridor runs at 7.2%. The layer is thin, as a supplementary layer should be, and each row carries the image ID for anyone to check.
- **Kept:** yes; it is what the map shows in the model colour. A first version left a stale cattle row behind on rerun; derived rows are now cleared per corridor before rewriting.

### E-023: integrity error on a visitor's browser after a deploy
- **What:** the owner opened the live site after two deploys in quick succession and saw "species.json failed its integrity check".
- **Why:** the service worker had precached the previous build's app shell (with the previous manifest compiled in); the data request carried a new `?v=` parameter that the precache did not match, so it went to the server and got the newer file. Old shell, new data.
- **Kept:** the precache now ignores the `v` parameter, so a cached shell is served its own cached data; and an integrity failure first updates the service worker, clears caches and reloads once, showing the error only if the mismatch survives that. Outdated caches are cleaned on activate.

### E-024: the cell drawer ignored the species filter, and the two data files disagreed on names
- **What:** the owner filtered the map to Wapiti, tapped a cell on the Madison River and got all 29 species of the cell, three bison photographs, and the name "American Elk" on the map against "Wapiti" in the species list. Searching "elk" found nothing.
- **Why:** three separate faults. The drawer built its rows from the unfiltered cells. The cell photo strip kept the top three photographs per cell, all bison in a busy cell. `cells.geojson` took the first common name seen per species while `species.json` took a plain majority; 9 of the park's species disagreed (American Elk/Wapiti, Mangrove Warbler/Yellow Warbler, Pink-sided Junco/Dark-eyed Junco, Northern Red-shafted Flicker/Northern Flicker…), and GBIF vernaculars like "Canada Goose unknown" could outvote iNaturalist's curated name.
- **Kept:** one rule for both files: the name most iNaturalist rows used, GBIF names only when iNaturalist has none; the losing names are exported as `other_names` and searched, so "elk" finds Wapiti. The strip keeps the top three plus the best photograph of every other species in the cell (`cell_pick`, with `cell_pick_v1` kept for the comparison test). With a filter on, the drawer leads with that species, its own photographs from that cell, a link to the same bounding box and taxon on iNaturalist so anyone can check the cell against the source, and folds the other species away.
- **Number:** name mismatches 9 → 7 → 0. The first fix still voted inside each exporter, and the cells file, which only sees open coordinates, named the Smokies' elk (1 open row, 468 obscured) from its single open row; the vote now runs once per park over every canonical row and both files read it. photos_cells.json for Yellowstone grew from 768 KB to 1.25 MB (loaded on the first cell tap, not with the app).

### E-025: landmarks for a virtual tour, from OpenStreetMap
- **What:** a walk-through needs stops. Wikipedia geosearch inside the park's bounding box returned hundreds of creeks and minor peaks with nothing separating a landmark from a tributary. OpenStreetMap features carrying a `wikidata` tag, in a short list of kinds (geyser, hot spring, waterfall, peak, lake, valley, pass, viewpoint, visitor centre, attraction, historic, place), fetched through Overpass and kept only inside the iNaturalist place polygon: Yellowstone 449 fetched → 97 kept (75 outside the boundary, 223 over the per-kind cap; 80 of the fetched features were geysers).
- **Failures on the way:** the per-kind cap ran before the curated tour was matched, so Old Faithful (the 21st geyser alphabetically) was cut and its visitor centre took the stop. Prefix matching gave "Norris Geyser Basin" the Norris museum. "Lower Falls" as a bare Wikipedia title is a disambiguation page. Fixed by matching first and capping second with stops exempt, letting a configured coordinate beat a fuzzy match, and per-stop `@wiki` article titles in config/parks.toml.
- **Numbers:** Yellowstone 11 stops, Grand Teton 8, Great Smoky 8, none missing; landmarks.json 22 / 16 / 14 KB; boundary.geojson 1 / 5 / 17 KB. Wikipedia summaries fetched once per stop at 1 request/s.

### E-026: a map of the park, not a diagram over one
- **What:** the owner's review of the map: flat grey positron, the whole country reachable, no sense of place. Replaced with OpenFreeMap "liberty" (roads, rivers, labels) under a hillshade and a 3D surface from the AWS Terrain Tiles (Terrarium PNGs, USGS 3DEP and SRTM), a USGS National Map imagery toggle, a wash over everything outside the iNaturalist park polygon, `maxBounds` a third of a park past the boundary, and a tour that flies stop to stop at a 60° pitch facing the next stop, listing the species recorded within 2.5 km with a photograph each.
- **Checked before building:** every tile and data endpoint answered 200 without a key and with `Access-Control-Allow-Origin: *` (USGS imagery and topo, the terrain bucket, the OpenFreeMap style and fonts, the iNaturalist place record, the Wikipedia summary endpoint).
- **Numbers:** MapPage chunk 19 KB (7 KB gzipped); the maplibre chunk is unchanged at 276 KB gzipped; three new CSP hosts.
- **Unresolved:** 3D terrain on low-end phones (it is off under `prefers-reduced-motion`, and a toggle); USGS tile service limits are undocumented for this volume; the outside-the-park wash hides the roads that lead into the park, which a visitor might want.

### E-027: integrity error again, on the first deploy after E-023
- **What:** the owner opened the live site minutes after the E-026 deploy and saw "species.json failed its integrity check (expected 19446acc…, got 5e653d26…)". The expected hash is the previous build's species.json, the received one is the new build's: an old app shell ran against new data.
- **Why:** E-023 fixed one path (old worker serving new data) but the shell itself can still be old: the browser or the GitHub Pages CDN had index.html and its bundle cached, the new worker took control on install (autoUpdate), and the recovery called `location.reload()`, which the same caches answered with the same old shell. The second attempt was blocked by the one-shot session flag, so the error stayed.
- **Kept:** the recovery now unregisters the worker, drops every cache and navigates to the same page with a `?fresh=<timestamp>` parameter, which nothing has cached; it may try again after 45 s and the error box has a Reload button that does the same by hand. Data files left the precache: each URL carries `?v=<hash>`, so a content-addressed runtime cache hands every shell exactly the files it was built with, and a first visit no longer downloads three parks in the background (precache 12 MB → 2.2 MB, shell only).
- **Unresolved:** a stale CDN edge can still serve an old index.html for up to ten minutes after a deploy; the fresh URL bypasses the edge for the document but the old bundle it references may be gone (404) in that window. Not seen yet; it would show as a blank page, not an integrity error.

## Open questions with a planned experiment

- **Q-1 SpeciesNet determinism.** Answered (E-013).
- **Q-2 Panorama slices vs whole panoramas.** Ablation: same 100 panoramas whole and sliced; compare animal-box rate and review precision.
- **Q-3 Country filter on/off.** Same frames with and without `--country USA`; count label changes.
- **Q-4 Mapillary's own `animal--ground-animal` tags as a pre-filter.** Fetch with `pull --with-mapillary-detections`; overlap with MegaDetector boxes >= 0.2.
- **Q-5 Trivial baseline.** Predict the most common reviewed species for every true positive; compare with SpeciesNet's species agreement.
