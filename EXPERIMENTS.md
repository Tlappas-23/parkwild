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

### E-028: directions inside the park without a routing service
- **What:** the owner wants "based on current location, click which sites and get the best route". No hosted router fits the brief: OSRM's public server is a demo that asks not to be used in production, GraphHopper and OpenRouteService need a key (public in a static site), Valhalla is a backend, Google is forbidden. So the park's own OpenStreetMap roads and trails are baked into a graph (`parkwild/roads.py`, `track_a.py roads`) and the browser runs Dijkstra and the visiting order itself (`app/src/routing.ts`: exact Held-Karp up to 9 sites, nearest-neighbour plus 2-opt beyond).
- **First pass:** every highway in the park's bounding box. Great Smoky came out at 8,000 km of road, 64k nodes and 8.9 MB: the streets of Gatlinburg, Pigeon Forge and Cherokee. Fix: outside the park polygon only motorway-to-tertiary roads survive, and service roads, living streets and parking aisles are dropped everywhere.
- **Numbers after the fix:** Yellowstone 2,510 ways (1,144 outside the boundary and 1,383 service dropped), 10,099 nodes, 721 km road + 1,824 km trail, 1.48 MB (403 KB gzipped); Grand Teton 4,299 nodes, 613 KB; Great Smoky 13,474 nodes, 2,071 km road + 1,421 km trail, 2.0 MB (562 KB gzipped). Loaded only when someone plans a route. Edges are cut every 300 m so a site snaps to a node at most 150 m off the road. Yellowstone Lake's landmark point is the lake's centre, 7.5 km from any road; the first pass called it unreachable, now the leg goes to the nearest road and says how far the point is.
- **Unresolved:** no closures, no seasons, no grades; the panel says so and links nps.gov. Speeds are assumed (35 mph, 5 km/h). One-way roads are honoured; turn restrictions are not. The device position is asked for only on a tap and never stored.

### E-029: the tour panel hid the map
- **What:** the owner: "the tour summary is a pop up and hides the map, I want it smaller so we always see the map".
- **Kept:** a slim bar (about 110 px on a laptop, one row of small photographs, two lines of text) with a "Details" toggle that grows it for the full paragraph and credits; the camera pads the view by the bar's measured height, so the stop always sits above it.

### E-030: a front door, a side dock, and arrivals
- **What:** the owner: "a cleaner version to switch parks: a home page with badges for the park; the tour not blocking the map; see the full outline of the park first, then zoom in; cool transitions from one spot to another".
- **Kept:** a home page with one card per park (`track_a.py index` → `app/public/data/parks.json`, imported at build time): live parks with species, sightings and stop counts, configured-but-not-exported parks as "coming soon". The card photograph is the park's Wikipedia lead image, taken only when Commons reports a reusable licence (10 of 11 parks; Glacier's is not) and credited on the card (ADR-0019). On wide screens the tour narration is a 320 px dock at the right edge with the species listed vertically and every photograph credited; the map keeps its full height and the camera pads to the side. On phones it stays a bar. The park outline got a white casing under a darker dash. Opening a park now arrives from a higher, tilted view and settles on the whole outline (1.7 s); switching parks glides across (2.2 s); stop-to-stop flights take 3 s on a wider arc.
- **Numbers:** parks.json 7.5 KB; the dock is 320 × (viewport − 28) px against the old card's 880 × 360.
- **Unresolved:** Commons' `Artist` field is free HTML (one credit reads "Shenandoah National Park from Virginia", the uploader's name); it is stripped to text and cut at 80 characters, not curated.

### E-031: every species peaks in June, and every model count is zero
- **What:** the owner, reading Grand Teton species pages: "are all of the models 0 and all the main months June or July?"
- **Model.** Yes, by construction. The imagery pass (Track B) ran on one corridor, Yellowstone's Lamar Valley, and confidently named three animals, all bison; 28 more are the unnamed-mammal bucket. Grand Teton and Great Smoky have no imagery pass at all. The badge now appears only in parks where a pass ran; elsewhere the page says "no imagery pass here yet".
- **Months.** Mostly yes, and it is effort, not biology: 64% of all Yellowstone sightings fall in June to August (63% Grand Teton, 45% Great Smoky). Of the 147 Yellowstone species with 20 or more records, 90 peak in June, 21 in July, 13 in September, 11 in August, 10 in May, 2 in January. Dividing a species' share of each month by everyone's share separates the two: bison ×1.7 in December, wapiti ×2.0 in November, pronghorn ×3.6 in November, coyote ×4.6 in January (Yellowstone); moose ×3.5 in December, Uinta ground squirrel ×1.9 in April, mule deer ×1.4 in September (Grand Teton); white-tailed deer ×3.4 in December, wapiti ×3.3 in October (Great Smoky). 69, 41 and 43 species respectively have their effort-adjusted peak outside summer.
- **Kept:** the species page shows "busiest month" and "seen more than usual" side by side, with a second bar row for the ratio (needs 30 records; fewer makes any month look special) and one sentence saying which is which. The ratio is a share of a share: it says when, not how many.

### E-032: the tour dock was still a wall
- **What:** the owner, on the 320 px full-height dock: "the tour block is also too big and covers the map so we lose sight of where everything is".
- **Kept:** a content-sized translucent card in the top-right corner (300 px wide, about 380 px tall, blurred backdrop so the map shows through), three-column thumbnails with tiny credits, three lines of text, and a minimise button that leaves a one-line strip with the stop name and the arrows. The camera pads only by the card's width. The phone bar is unchanged.

### E-033: making the camera pass count for something (owner's choice of 1 and 2, 2026-09-05)
- **What:** the owner, on "model 0" everywhere: "obviously that's not good". Options offered: (1) a second, larger review to measure species-label precision by classifier score and move the naming bar if the numbers allow; (2) present the pass as what it is, a method with its own numbers, rather than a badge competing with human sightings; (3) a different sensor. Chosen: 1 and 2, "as long as it's free". Both are.
- **Built for (1):** `phase0.py species-sample` draws boxes the map already shows (detector ≥ 0.5) from every corridor with detections, 30 per classifier-score band (0.5–0.6, 0.6–0.7, 0.7–0.8, 0.8+), renders the frame and crop, and writes `data/review/species/perspective/review_<reviewer>.csv` with the same columns as Phase 0 (`verdict`, `true_species`, `species_agree`). `phase0.py species-report` loads it and prints animal precision and species precision per band with Wilson intervals, and the lowest naming bar every band at or above clears 60% on at least 15 judged boxes. The bar in `trackb.SPECIES_MIN_SCORE` moves only to a number that report prints, and the change cites it.
- **Built for (2):** `camera_pass.json` per park (in the manifest): per corridor, images indexed, frames scored, frames with an animal, sightings, named species, imagery months and years, contributors, and Phase 0 precision with its interval where a review exists; corridors with no run yet are "planned". The About page shows the table; the map draws each corridor as a dashed box in the model colour labelled with its count or "queued"; the species page shows the model badge only when the count is above zero and otherwise links "how it works".
- **Queued:** the pass on Moose-Wilson (Grand Teton), Cades Cove (Great Smoky) and Hayden Valley (Yellowstone) on CPU after the park ingest; the species sample is drawn once those finish so it covers four corridors.
- **Expected honestly:** tens of model sightings per corridor. The pass sees what a car sees; nothing here changes that.

### E-034: the app never updated itself
- **What:** the owner sent a screenshot of the two-column tour card, four deploys old, asking again for a home page that already existed. Their tab had never received a newer build.
- **Why:** `registerType: "autoUpdate"` in vite-plugin-pwa only calls `skipWaiting()` on a `SKIP_WAITING` message, which the old shell never sends, and does not claim clients. So each new worker installed and then waited for every tab of the old one to close. Meanwhile the old shell and its precached data agreed with each other, so the integrity check (E-023, E-027) had nothing to object to. A visitor who never closes the tab, or reopens the site from history, stays on the first build they ever saw.
- **Kept:** the worker now skips waiting at install and claims open pages (`skipWaiting`, `clientsClaim`); the app reloads on the controller change when it happens within 30 s of opening, and otherwise shows a "newer version is ready" pill so a tour or a plan is never yanked away. Existing stale tabs pick this up on the next worker update check, which GitHub Pages' ten-minute cache bounds; closing every tab of the site once does it immediately.
- **Number:** the owner's screenshot was build 4 of 8 that day.

### E-035: pictures from there, a closer camera, and motion during the tour
- **What:** the owner, on the corner card: the legend collided with the left panel once the planner opened; the tour's photographs should look like they were taken at the stop; the camera should be closer and the map should move while the tour runs.
- **Kept:** the legend sits bottom-right above the zoom buttons on wide screens (hidden on phones while touring). Each species on a stop's card now shows a photograph taken inside the stop's 2.5 km radius when one exists, found through the cell strips (one photograph per species per cell) and the galleries' cell ids, tagged "near here"; otherwise the species' park-wide photograph, said so in the tooltip. Stops land at zoom 13.3 and 64° pitch (was 12.4 / 60°) and, once the flight ends, the camera turns 45° over the 14 s dwell; a drag, the next flight or leaving the tour stops the turn.
- **Number:** on Yellowstone's eleven stops, 32 of the 33 species cards show a photograph taken within 2.5 km of the stop (Yellowstone Lake: 2 of 3). Not curated; the cell strips decide.

### E-036: things to do around each stop
- **What:** the owner: "add things to do within each of the main sites, key features, where to camp, hike, trails". And, mid-work: keep the UI clean and professional.
- **Kept:** `track_a.py amenities` pulls one Overpass query per park: campsites and RV sites, huts and lodges, trailheads, viewpoints, picnic sites, visitor centres and ranger stations, boat launches, and named natural features; facilities inside the park polygon, camping and lodging anywhere in the bounding box because the campground for a stop is often outside the gate. Named trails come from the routing graph already baked: every trail edge with a name, summed by name (Yellowstone: 246 trails, 1,593 km). The tour card gets a second tab, "Things to do", grouped Key features / Hike / Camp / Stay / Also here, nearest first, with fees, capacities and reservation tags copied as OSM has them, an add-to-route button per item, and the same items drawn on the map in a colour per kind while the tab is open. The planner's search now finds named campsites, trailheads and features too.
- **Numbers:** Yellowstone 1,640 items (951 named features, 334 campsites, 103 lodgings, 96 viewpoints, 61 trailheads, 54 picnic sites, 37 visitor centres or ranger stations, 4 boat launches), 319 KB; Grand Teton 265 items, 98 trails; Great Smoky 1,050 items (375 lodgings, mostly Gatlinburg and Cherokee in the bbox), 211 trails. "Near" is 3 km for features, trails and facilities, 12 km for camping and lodging, at most six per group.
- **Unresolved:** OSM's campsite coverage mixes backcountry sites ("4R1") with drive-in campgrounds; the `backcountry` tag separates them only when present. The NPS API (free key, public domain) would add reservations, seasons and official "things to do"; left as the next enrichment.

### E-037: how photorealistic can a free 3D map of a park get?
- **What:** the owner: "how do we get this to be a photo-realistic 3D map of what we are actually looking at". Measured what the free, keyless sources allow, then took what they give.
- **Ceilings measured (2026-09-05, Old Faithful):** USGS The National Map imagery stops at zoom 16 (about 2.4 m per pixel at 44°N; zoom 17 and up return 404). The USDA NAIP image service did not answer. The AWS terrain tiles stop at zoom 15 (about 5 m). Esri's World Imagery answers keyless to zoom 19 with CORS, but its terms for third-party apps now ask for an API key; recorded as O-10, not used. Photogrammetry meshes of the Google Earth kind exist only from Google and Apple; Google is excluded by the brief and Apple has no web offering.
- **Kept:** on imagery the terrain exaggeration drops to 1.12 (true relief reads right on photographs; 1.35 stays for the paper style), the pitch ceiling rises to 78°, and every tour stop gains what the aerial view cannot show: up to six photographs taken within 400 m from Wikimedia Commons under reusable licences (the park-card rule, ADR-0019), credited with artist, licence and distance, plus a "look around from here" link to the nearest Mapillary image within 300 m (a panorama when one is as close), linked by id with the contributor's name and CC BY-SA; the picture itself is never copied. The token is used in the pipeline only.
- **Numbers:** printed per park by `track_a.py landmarks` (stop_photos, stops_with_street); Old Faithful: 6 photographs within 4 m, all CC BY-SA 3.0.
- **Unresolved:** past zoom 16 the imagery blurs; a sharper free source would change the whole feel and none is clean today. Commons geosearch ranks by distance, not quality; a "quality image" filter would need a second query per file.

### E-038: the left panel folds away
- **What:** the owner: "can we hide the left panel as well".
- **Kept:** a collapse button on the panel and a "Filters" pill in the corner that reopens it and shows the active species and whether a route is being planned; the panel folds on its own when a tour starts and returns when it ends, so a tour is map, card, nothing else.

### E-039: every place opens
- **What:** the owner: "there should be details for the trails, pictures etc. so when you click on it you can see which animals, how long the trail is, site summary and history".
- **Kept:** a place drawer for any trail, feature, campsite, lodge, viewpoint or landmark, opened from the tour's things-to-do list, from its marker on the map, or from a landmark dot. It shows the facts OSM has (trail length from the routing graph, elevation, capacity, fee, reservation, difficulty, surface), a summary from Wikipedia (the tagged article, or a search restricted to hits that carry the place's own name, or an honest "no article"), the animals recorded there with a near-here photograph each (along the whole trail within 300 m of its line, using the trail's geometry from roads.json; within 1 km of a point), a one-click filter of the map to the top species, and licensed photographs of the place within 400 m from Wikimedia Commons. The two lookups run in the browser at click time against free, cross-origin endpoints; only a title or a coordinate leaves the browser. The trail is drawn whole on the map and the view frames it.
- **Numbers:** 108 of Yellowstone's 1,640 places carry a Wikipedia tag; the rest go through the name search. Species along a trail come from the cells its line passes through, so a 10 km trail is tens of cells, not one.
- **Unresolved:** the name search can miss (a trail named after a creek lands on the creek's article, which is usually what a reader wants) or decline; both are shown as they are. Photographs are nearest-first, not best-first.

### E-040: the design system pass
- **What:** the owner: "how would this be approved by Apple… this needs to be better… the best". Measured against what a senior design review flags: four button styles, ad-hoc unicode glyphs for icons, five semantic colours for place kinds, credits at 9 px, a home page without a hero, panels that were containers of controls rather than designed surfaces.
- **Kept:** one token set (one accent, one warning colour for the model, neutrals; a type scale from 11 to 32; an 8-pt spacing scale; three radii; one shadow; one easing), one button family (pill, small, icon; primary, ghost, toggle, segmented), Lucide icons everywhere a glyph was, credits at 11 px minimum, focus rings on every control, enter animations for panels and tab content that respect reduced motion, places in one slate colour with the kind carried by an icon, the route in the accent and the open place in ink, the home page opening on a full-bleed credited photograph of a live park with the park search inside it, and the left panel starting folded on phones.
- **Not done yet:** a designed logo and share image; bottom-sheet gestures on phones; a Lighthouse and axe pass in CI (Phase 7).

### E-041: AI on the visitor's device, measured before it is trusted
- **What:** the owner: "incorporate AI and be a good source, all free". Built as ADR-0021: a language model and an image model run in the browser after an opt-in download; the language model may only write from numbered facts built from the park's own data and must cite them; the image model ranks a photograph against the park's species names as a suggestion.
- **Measured:** the eval set (docs/ai-eval.md) ran end to end in the automation browser only with a 360M model, because that profile refuses to store more than about 300 MB per origin in Cache storage, the private file system or IndexedDB (the download itself ran at 20 MB/s). The run exercised the fact builder, the citation parsing, the streaming and the checks, and showed the 360M model misreading facts freely; it is not offered to visitors. The default 1.5B model's table is pending the first run on the live site, which the Ask page's "Measure it" control produces for anyone.
- **Fixed on the way:** species matching now goes by distinctive words with plurals ("bison" → American Bison, "elk" → Wapiti, "bear" → both bears; a bare generic word only when unambiguous); the invention check ignores list numerals and citation markers and counts numbers of three or more digits; the model store falls back from Cache storage to the private file system to IndexedDB on quota refusals; storage failures read as one plain sentence.
- **Unresolved:** made-up words pass the number check ("Trumpeter SQUARE"); a name check against the fact text is the next addition. The WebLLM chunk is 2.1 MB gzipped and loads only when Ask is enabled.

## Open questions with a planned experiment

- **Q-1 SpeciesNet determinism.** Answered (E-013).
- **Q-2 Panorama slices vs whole panoramas.** Ablation: same 100 panoramas whole and sliced; compare animal-box rate and review precision.
- **Q-3 Country filter on/off.** Same frames with and without `--country USA`; count label changes.
- **Q-4 Mapillary's own `animal--ground-animal` tags as a pre-filter.** Fetch with `pull --with-mapillary-detections`; overlap with MegaDetector boxes >= 0.2.
- **Q-5 Trivial baseline.** Predict the most common reviewed species for every true positive; compare with SpeciesNet's species agreement.
