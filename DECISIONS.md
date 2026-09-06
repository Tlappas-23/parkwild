# Decisions

Architecture Decision Records. One entry per choice that someone might later ask
"why?" about. Format: context, decision, alternatives rejected, consequence.
Backfilled on 2026-09-05; new entries are appended, never rewritten.

## ADR-0001: Adopt the stack as given in the brief

**Context.** The brief fixed Mapillary, Overpass, MegaDetector/SpeciesNet,
iNaturalist, DuckDB, MapLibre, and free compute, and asked that disagreements be
reported rather than substituted.
**Decision.** Use it unchanged. Nothing in the stack was found wanting during
Phase 0.
**Rejected.** The `mapillary-python-sdk` the docs suggest for large areas: a
thin client of our own is smaller, testable, and handles the two undocumented
behaviours below.
**Consequence.** Every module in `src/parkwild` maps to one row of the stack.

## ADR-0002: Three decoupled tracks

**Context.** The detection pipeline (Track B) may not work. The build spec
requires a shippable app regardless.
**Decision.** Reference data (Track A: iNaturalist + GBIF) and detection (Track
B) both write to one `sightings` schema with `source` and `confidence_basis`
columns. The app (Track C) reads the schema only.
**Rejected.** Building the app on detection output first, then adding reference
data as validation. That couples the product to the unproven part.
**Consequence.** Phase 0 routes; it does not gate. Track A started 2026-09-05.

## ADR-0003: Python 3.12 venv; SpeciesNet runs as a subprocess

**Context.** SpeciesNet 5.0.5 requires Python < 3.15 and pins `yolov5`, whose
wheels lag new Pythons. Homebrew's Python is 3.14. Importing torch into the
pipeline package would drag it into every test and the notebook.
**Decision.** `.venv` from Anaconda's 3.12. `speciesnet_runner` shells out to
`python -m speciesnet.scripts.run_model` and parses its JSON.
**Rejected.** Importing `speciesnet` directly: heavier import graph, and it
would lose SpeciesNet's own resume-from-JSON behaviour.
**Consequence.** The light venv has no PyTorch; `make setup-ml` is a separate,
explicitly approved step.

## ADR-0004: Mapillary crawl splits at 1500 rows and on HTTP 500

**Context.** Documented: bbox searches must be under 0.01 deg² and pagination
only works with `creator_username`. Measured 2026-09-05: tiles returning 1879
to 1973 rows were truncated (their quarters summed to 2500 to 3400) while 1849
and below were complete; two Cades Cove tiles returned HTTP 500 at any `limit`
while their quarters answered normally.
**Decision.** Treat ≥ 1500 rows as capped and quarter the tile; treat a repeated
5xx on a splittable tile as "too heavy" and quarter it; record an unsplittable
error tile as `error` and retry it next run.
**Rejected.** Trusting `len(rows) < 2000` as complete: it under-counted Lamar
Valley by a third.
**Consequence.** More requests on dense tiles (Lamar: 101 tile queries instead
of 21). Complete enumeration.

## ADR-0005: Lamar Valley is the Phase 0 corridor

**Context.** Coverage 2026-09-05: Lamar 27,430 images / 55 sequences / 2014 to
2024; Moose-Wilson 24,231 / 88; Cades Cove 39,410 / 123 / to 2026-06.
**Decision.** Lamar Valley, the brief's first pick and the best case for
sightlines and animal size. If detection fails here it fails everywhere.
**Rejected.** Cades Cove: denser and more recent, but forest-edge deer and
turkey are a harder detection case. It is the natural second corridor.
**Consequence.** Phase 0 measures a Wyoming open-valley population; Cades Cove
would test forest generalisation in Phase 2.

## ADR-0006: Two Phase 0 populations, reported separately

**Context.** 87% of Lamar's images are 4096 x 2048 spherical panoramas from one
contributor in June 2024; the 3,690 perspective frames are 2014 to 2018.
**Decision.** Sample and report both: 400 perspective frames whole, and a set
of panoramas sliced into four 90° yaw windows of the horizon band. Slicing
fixes projection distortion and object-to-frame ratio. It does not add pixels:
a 4096-wide panorama is about 11 px per degree, so a bison at 100 m is about
11 px tall in it, sliced or not.
**Rejected.** Perspective-only (ignores the dominant population); running
whole panoramas through MegaDetector (the model resizes to 1280 px on the long
side, so everything becomes 3 to 7 px).
**Consequence.** `variant` column on the raw prediction tables (`full`,
`yaw000`, `yaw090`, `yaw180`, `yaw270`); every Phase 0 number is reported per
population.

## ADR-0007: Raw model output is append-only

**Context.** The brief and the spec both require that corrections never
overwrite predictions.
**Decision.** `predictions_raw` and `detections_raw` are written with
`INSERT OR IGNORE` keyed by (image_id, model_version, variant[, det_idx]).
Human verdicts go to `manual_review`. Run metadata goes to `runs`.
**Rejected.** `INSERT OR REPLACE` (the scaffold's first version): a rerun with
different thresholds would silently rewrite history.
**Consequence.** Re-scoring with a new model is a new `model_version`, and
accuracy is a join against `manual_review` for any version.

## ADR-0008: Security model: single writer, public reader, optional read gate

**Context.** Owner asked for "authentication for web and app" and "tight
security so no one can write over what I build." The spec says the app is
publicly reachable with no auth and no backend.
**Decision.** Lock every write path to the owner (private repo, protected
`main`, CI-only deploys, secret scanning, append-only raw data, hashed
artifacts). Keep reads public by default. Document Cloudflare Access (free, up
to 50 users) as the one-toggle read gate if the owner wants a private preview
or a private launch.
**Rejected.** A backend with user accounts: costs money at scale, adds a write
surface, and the spec forbids it. A paid auth service: forbidden by budget.
**Consequence.** SECURITY.md is the checklist. Whether to enable the read gate
is an open decision for the owner.

## ADR-0009: No recall figure; precision with a Wilson interval

**Context.** There is no exhaustive annotation of frames, so recall cannot be
measured; a number would be invented. Thirty reviewed boxes give a wide
precision interval that a bare percentage would hide.
**Decision.** Report precision as a point estimate with a 95% Wilson interval
and the counts behind it. Report recall as "unmeasured", everywhere.
**Rejected.** Estimating recall from a hand-scanned subset: the subset would be
too small to mean anything and would be presented as if it did.
**Consequence.** `report.py` prints the interval; the About page will say
"unmeasured".

## ADR-0010: Review samples stratified by confidence band

**Context.** Sampling the top-N boxes by confidence inflates precision.
Sampling uniformly over-represents the 0.2 to 0.5 band where most boxes live.
**Decision.** Equal allocation across three detector-confidence bands (0.2 to
0.5, 0.5 to 0.8, 0.8 to 1.0), at most one box per frame, deterministic order
from a seeded hash.
**Rejected.** Top-N (inflates), uniform (uninformative about the high band).
**Consequence.** Precision is reported per band as well as overall.

## ADR-0011: GBIF ingest skips the iNaturalist mirror; eBird is opt-in pending a decision

**Context.** GBIF counts for the Yellowstone bbox on 2026-09-05 (human and
machine observations with coordinates): Mammalia 26,248, of which 25,292 are
GBIF's mirror of iNaturalist research-grade observations. Aves 445,426, of
which 421,940 are eBird checklists and 16,280 the iNaturalist mirror.
**Decision.** Skip the iNaturalist dataset in GBIF outright: it is an exact
copy of what the direct iNaturalist ingest already stores, and skipping it by
dataset key is more reliable than fuzzy deduplication. Ingest every other
dataset for both classes. Do not ingest eBird until the owner decides whether
birds at that volume are in scope; the code supports it (`--include-ebird`,
year-split paging past GBIF's 100,000-offset cap).
**Rejected.** Ingesting eBird by default: 421,940 rows would be 90% of the
park's data, dominated by checklist locations (often a hotspot rather than
where the bird was), and would make the bird layer the app rather than a
layer of it. Dropping GBIF for birds entirely: the ~7,000 non-eBird,
non-iNaturalist records are real and cheap.
**Consequence.** Bird counts in the app understate what eBird knows until the
decision is made; species.json and the About page must say so. Logged in
reports/decision_log.jsonl by the ingest.

## ADR-0012: SpeciesNet runs on CPU on this machine

**Context.** Decision 1 chose a local install and required a determinism
check with a CPU fallback on any misbehaviour. Measured (E-012): MPS
segfaulted at 20 frames (batch 8) and aborted (batch 1) inside SpeciesNet's
classifier preprocessing, and hung in multi-process mode; CPU completed.
On the three frames where MPS did run, it matched CPU exactly.
**Decision.** CPU is the default backend (`--backend cpu`, via
scripts/speciesnet_cpu.py which hides MPS from torch). Every run records its
backend in the `runs` table.
**Rejected.** Debugging the MPS crash inside torch/speciesnet: not this
project's problem to fix, and the cost is minutes per corridor, not hours.
**Consequence.** Inference on 400 originals is roughly half an hour instead
of ten minutes. Revisit when torch or speciesnet changes version; the
determinism script is the test.

## ADR-0013: Phase 0 routing for Track B: supplementary layer (confirmed by owner 2026-09-05)

**Context.** Lamar Valley, 400 perspective frames, SpeciesNet 4.0.3a on CPU,
stratified review of 20 boxes by one reviewer. Hit rate 8.2% (CI 6 to 11%).
Precision 42% (95% CI 23 to 64%, n=19); by band 0.2 to 0.5 33% (95% CI 12 to 65%, n=9), 0.5 to 0.8 44% (95% CI 19 to 73%, n=9). All true
positives bison at 45 to 150 m; nothing found beyond 150 m. Six of eleven
false positives are people the ensemble correctly labels "human"; four are
lone conifers. Trivial baseline for species (always "bison") beats the
classifier, 8/8 vs 5/8.
**Panorama population (E-018).** 100 panoramas, 17 boxes reviewed: precision
2/16 (12%, CI 3 to 36%); seven false positives are the camera's own
mounting arm in the yaw090 window, every box in the mid band. Negative
result as processed; the rig is maskable.
**Decision (proposed).** Track B becomes a supplementary layer built on
perspective frames only: crawl only best-coverage corridors, surface as
model-predicted and visually distinct, filter ensemble label "human" /
"vehicle" out of the animal layer, treat species labels as no better than
"large mammal" until a multi-species corridor says otherwise, and keep
panoramas out until the rig region is masked and the population re-read.
**Why not primary.** The precision point estimate is below 60% and the top
band that a UI would threshold at has one box in 400 frames.
**Why not negative.** Real bison are found at 8% of frames with confirmed
range to 150 m, and the false positives have shapes (people, lone trees) that
cheap filters address.
**Consequence.** Phase 2 scoped to corridors with Lamar-like coverage;
panorama population still to be read; a second reviewer's pass changes the
interval, not the band, unless it disagrees on more than three boxes.
**Status.** Confirmed by the owner on 2026-09-05 after both populations were
read. Phase 2 proceeds at supplementary scope: Lamar Valley perspective
frames in full, human/vehicle ensemble labels filtered out of the animal
layer, species shown as "unidentified large mammal (model)" unless the
classifier is confident, positions at the camera with the measured 150 m
range as the stated uncertainty, panoramas excluded until the rig is masked.

## ADR-0014: How Track B enters the sightings table at supplementary scope

**Context.** ADR-0013 routed Track B as a supplementary layer. The raw
tables hold one row per box with a camera position; the app needs one row
per sighting in the shared schema, visibly model-predicted.
**Decision.** `parkwild/trackb.py`: animal boxes at detector confidence >=
0.5 whose ensemble label is not human, vehicle or blank; consecutive frames
in a sequence within 60 s and 200 m collapse to one sighting (the strongest
box); position is the camera position with 150 m, the farthest confirmed
detection, as the stated accuracy; the species is named only when the
classifier scores >= 0.8, otherwise "unidentified large mammal (model)";
Mapillary image ID, contributor, licence and page URL on every row; the
compass bearing is stored for Phase 4 projection.
**Rejected.** Placing points along the bearing now: no range estimate exists
yet (Phase 4). Trusting species labels: the trivial baseline beat the
classifier in Phase 0. Keeping "vehicle"-labelled boxes: two reviewed bison
were labelled vehicle, but so were real vehicles; without a larger review
the filter stays and the loss is recorded.
**Consequence.** The map shows model-predicted cells in a distinct colour
with their own badge; species.json carries the Mammalia bucket; the About
page states the 42% Phase 0 precision. All thresholds are tagged in the
module with the counts behind them and move only with a bigger review.

## ADR-0015: Photographs are the evidence, under strict licence rules

**Context.** The owner's review of the first live app: aggregated hexagons
and monogram tiles show neither the animal nor proof of the place. Every
iNaturalist record's raw JSON is stored, and 89,238 photographs come with
per-photo licences.
**Decision.** Show iNaturalist photographs as the species card art, the
species hero and gallery, and a "seen here" strip in the cell panel, only
under CC0, CC BY, CC BY-SA, CC BY-NC and CC BY-NC-SA (62,222 of 89,238),
always with the observer's name, the licence and a link to the observation,
hotlinked from iNaturalist's CDN. No-derivatives and all-rights-reserved
photographs are not shown at all. Sensitive-species rules match the cells:
excluded species get no cell photos, coarsened species attach to the coarse
cell, obscured coordinates attach to no cell. Model-predicted sightings link
to their Mapillary image by ID and show no thumbnail (ShareAlike caution in
the spec).
**Rejected.** Mirroring photographs into the repository (would make the repo
the publisher). Showing ND photographs at reduced size (a resized copy is
arguably a derivative). Rendering 3D thumbnails for cards (needs the models
first; photographs are better evidence anyway).
**Consequence.** photos_species.json (176 KB) loads with the app;
photos_cells.json (768 KB, 220 KB gzipped) loads on the first cell tap.
The CSP allows the two iNaturalist image hosts. Credit is printed beside
every image by one component, PhotoCredit.

---

## ADR-0016: The map is of the park: free relief, imagery, an outline and a guided tour

**Context.** The owner's review (2026-09-05): "get the map better rendered
so it looks like a real map… just of the parks… a virtual walk through with
major landmarks and where animals are sited". The hard constraints still
hold: zero cost, no key, never Google.
**Decision.** Basemap OpenFreeMap "liberty" (OpenStreetMap, ODbL). Relief
and 3D surface from the AWS Terrain Tiles bucket (Terrarium PNGs, open
data). Satellite toggle from USGS The National Map imagery (public domain).
The park outline is the iNaturalist place polygon the sightings were
filtered by; everything outside it is washed out and the camera cannot
leave a padded box around it. Landmarks are OpenStreetMap features with a
Wikidata link (E-025); the tour is a curated, ordered stop list per park in
config/parks.toml with Wikipedia's opening paragraph (CC BY-SA 4.0, linked)
and the species recorded within 2.5 km of the stop (open-coordinate cells
only; coarsened sensitive-species cells never attach to a landmark).
**Rejected.** Google Maps or Street View (forbidden by the brief). Mapbox
(key, paid tiers). Esri World Imagery without a key (terms unclear). USGS
Topo raster as the base (labels blur and rotate when the map is pitched).
NPS boundary shapefiles (a national download for three outlines).
**Consequence.** Three more CSP hosts. The service worker caches the new
tiles like the basemap. Landmarks and boundary files are integrity-hashed
in the manifest like every other data file. Attribution for every source
is on the map's attribution control and the About page.

---

## ADR-0017: Parks come from config; the app lists whatever was baked

**Context.** config/parks.toml already described Grand Teton and Great
Smoky Mountains; the app hardcoded Yellowstone.
**Decision.** Every Track A command takes `--park`. The manifest carries the
park's display name, so the app's park list is exactly the data folders
compiled into the build, switched with a select and `?park=` in the URL.
Suppression and the taxonomy map apply to every park; the auto-sensitive
rule is computed per park.
**Consequence.** Grand Teton and Great Smoky Mountains ingested 2026-09-05
(numbers in RESULTS.md). The imagery track (Track B) and its bias figures
exist only for Yellowstone's Lamar Valley until the other corridors are
pulled.

---

## ADR-0018: Directions are computed in the browser from the park's own road graph

**Context.** "Based on current location, click which sites and get the best
route" (owner, 2026-09-05). Zero cost, no backend, no key in a public page.
**Decision.** Each park's OpenStreetMap roads and trails become a graph
(`roads.json`, hashed into the manifest like every data file); the browser
snaps start and sites to it, runs Dijkstra per site, orders the visit
exactly for up to nine sites, and draws the legs. Driving uses roads only;
hiking uses trails too. Every leg links to OpenStreetMap's own directions
page for turn-by-turn. Position comes from the browser's geolocation API on
a tap, is never sent anywhere and never stored.
**Rejected.** OSRM's demo server (terms), GraphHopper and OpenRouteService
free tiers (keys), self-hosted Valhalla (a backend), Google Maps (the brief).
**Consequence.** One more file per park (0.6 to 2 MB, gzipped a quarter of
that), loaded on demand. Routes ignore closures and seasons and say so.
`Permissions-Policy` allows geolocation for the page itself only.

---

## ADR-0019: Park photographs come from Wikimedia Commons under the licence Commons states

**Context.** The home page wants a landscape per park. The project's own
photographs are of animals, and only iNaturalist's.
**Decision.** Use each park's Wikipedia lead image, but only after asking
Commons for the file's licence: public domain, CC0, CC BY or CC BY-SA pass;
GFDL-only, fair use and anything unstated do not. The card prints the
artist, the licence and a link to the Commons file page. The image is
hotlinked at 1,280 px; the CSP allows upload.wikimedia.org for images only.
**Rejected.** NPS galleries (public domain but no per-photo metadata to
keep); showing the lead image without checking (most are fine, some are
not, and "most" is not the standard here).
**Consequence.** Re-running `track_a.py index` keeps heroes already found
and only looks up the missing ones. A park without a reusable lead image
gets its initials on a plain card until an editor changes the article.

---

## ADR-0020: The species-naming bar moves only on a measured number

**Context.** Track B names a species only when the classifier scores 0.8
or better (ADR-0014); at Lamar that named three animals. The owner wants
the model to count for more.
**Decision.** A second review, stratified by classifier score, measures
species-label precision per band. `SPECIES_MIN_SCORE` is lowered to the
lowest band boundary such that every band at or above it is right at least
60% of the time on at least 15 judged boxes (`report.species_precision`).
If no band qualifies, the bar stays. Whatever the outcome, the pass is
presented on its own terms: where it ran, what it found, how good it was
(`camera_pass.json`, the About page table, corridor boxes on the map).
**Rejected.** Lowering the bar by feel (would put wrong animals on the map
at a known ~44% rate); hiding the pass entirely (it is the project's own
method and its numbers are part of the record); fine-tuning on the review
set (too few labels; docs/finetuning-decision.md).
**Consequence.** The owner reviews about 120 boxes. Named model sightings
rise if and only if the numbers allow. Recall stays unmeasured.

---

## ADR-0021: AI runs on the visitor's device and may only write from the record

**Context.** The owner wants the site to "incorporate AI" and stay free.
Hosted models cost money or need a key; a key in a static site is public;
and a model that knows things is a model that invents things.
**Decision.** Two models run in the browser after an explicit download:
Qwen2.5 1.5B Instruct (Apache-2.0, 4-bit, about 1 GB) through WebLLM over
WebGPU, and CLIP ViT-B/32 (MIT, about 150 MB) through Transformers.js. The
language model answers only from numbered facts assembled from the park's
own exports (species counts and seasons, busiest cells named by the nearest
landmark, landmarks and their Wikipedia lines, trails, campsites, the camera
pass numbers, and a computed route plan when asked for one); it must cite a
fact for every sentence and must say "the data doesn't say" otherwise. The
answer view shows which facts were cited and flags any number the model
wrote that is in no fact. The image model ranks a photograph against the
park's species names and is labelled a suggestion, never an identification.
Nothing typed or photographed leaves the device. A fixed question set is
run and its results recorded (docs/ai-eval.md) before any change to the
prompt, the facts or the model.
**Rejected.** Hosted APIs (cost, keys, data leaving the device); a larger
on-device model (download and memory on phones); retrieval by embeddings
(a second model to download for a gain the name matching does not need
yet); letting the model answer from its own knowledge (unfalsifiable here).
**Consequence.** Three CSP additions (wasm evaluation, the model hosts),
two lazy chunks that ship only when enabled, the onnx runtime copied into
the app at build time so no CDN is called at run time, and a documented
ceiling: a 1.5B model misreads facts sometimes; the facts stay on screen.

---

## ADR-0022: No 3D animal models

**Date:** 2026-09-06. **Status:** accepted.

**Context.** BUILD_SPEC Phase 6 planned a stylised 3D model beside the
photographs on some species pages. The viewer, the ingest script, the
credit lines on the About page and a sourcing sheet were built; no file was
ever downloaded, because each download was a browser action with the licence
read from the page first, and it never happened. Zero species in zero parks
had a model, and the About page said so.

**Decision.** Remove the track: the viewer and its two dependencies (an
875 KB chunk that never loaded), the `model` field in species.json, the
ingest script, the models config and folder, the sourcing sheet, O-5.

**Why.** The photographs are the stronger content; low-poly animals beside
observer photographs read as a toy against the site's look. The spec's own
rule already forbade the one striking use, an animal placed at a precise
spot, because positions are approximate and sensitive species are coarse.
Weight and maintenance for nothing.

**Consequences.** Species pages are photographs, months, sources and the
park-by-park section. Nothing visible changes. Shipped species.json files
keep a `"model": null` key until their next export; the app ignores it.

## Open decisions (owner's call; recorded here so nothing is decided by drift)

| # | Decision | Default until decided | Where |
|---|---|---|---|
| O-1 | Run SpeciesNet locally (`make setup-ml`, several GB) or on Kaggle | **decided: install** (2026-09-05); MPS with determinism check, CPU fallback | RESULTS.md Phase 0 |
| O-2 | Create the private GitHub repo and push (`Tlappas-23`), then `make protect` | **decided: yes** (2026-09-05); pushed to github.com/Tlappas-23/parkwild; protect failed, see O-7 | SECURITY.md |
| O-3 | Enable the Cloudflare Access read gate at launch | **decided: public** (2026-09-05), with the species suppression list (config/suppression.toml) | ADR-0008 |
| O-4 | Ingest eBird (421,940 Yellowstone records) | **decided: skip** (2026-09-05); revisit only for checklists with GPS tracks | ADR-0011 |
| O-5 | Quaternius pack license: CC0 (pack page) vs QAL v1.0 (site license page) | closed 2026-09-06: the 3D track was removed before any file was downloaded (ADR-0022) | EXPERIMENTS.md E-052 |
| O-6 | Start the app skeleton (React + Vite + MapLibre + R3F; `npm install` is several hundred MB) | **decided: yes** (2026-09-05) | BUILD_SPEC.md Phase 5 |
| O-7 | Repo visibility: GitHub only protects `main` server-side on public or paid repos. Make it public (protection on, code visible, no secrets in it) or stay private with the local pre-push guard only | **decided: public** (2026-09-05); `main` protected server-side, local guard kept | SECURITY.md |


### O-8: where park data lives once there are 63 parks (raised 2026-09-05)

Each park adds 3 to 6 MB to `app/public/data/` (cells, photos, roads,
parquet), all of it re-exported and re-committed on every pipeline change.
Sixty-three parks is about 250 MB in the repository and in the Pages
build, and git history grows by that much per re-export. Options: (a) keep
going and accept a fat repo; (b) publish data from a separate orphan
branch or repository that CI writes and Pages serves alongside the app;
(c) GitHub Releases assets fetched at runtime (CORS allows it) with the
manifest still baked into the app. **Recommendation: (b)**, before the tenth
park. Until decided, parks are added a few at a time.

**Resolved 2026-09-06 (E-051): (a), with the parquet taken out.** The app never
read `sightings.parquet` and it was the largest file in every park folder
(3.5 of Yellowstone's 9.2 MB); it stays in `data/export` for anyone who wants
the table. Without it, 63 parks are about 120 MB in the repository and the
Pages build, well inside the limits, and history grows only by what actually
changes. Publishing goes through `scripts/publish_data.sh`, a data-only PR
from a fresh worktree, so code and data never share a commit. (b) stays the
next step if the repository passes about 500 MB.

### O-10: sharper aerial imagery from a source whose terms are not clean (raised 2026-09-05)

USGS imagery ends at zoom 16, which blurs in the pitched close-ups the tour
uses. Esri's World Imagery serves to zoom 19 without a key, with CORS, but
Esri's current terms expect an API key and attribution for use outside
ArcGIS; the keyless endpoint is legacy and could close. Options: (a) stay
with USGS and keep the camera above zoom 16; (b) Esri with attribution,
accepting the terms risk and a possible sudden outage; (c) an Esri
developer key (free tier, 2 million tiles a month), which puts a key in a
public page. **Recommendation: (a)** until a public-domain source improves;
revisit if the USDA NAIP service comes back.
