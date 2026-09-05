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

---

## Open decisions (owner's call; recorded here so nothing is decided by drift)

| # | Decision | Default until decided | Where |
|---|---|---|---|
| O-1 | Run SpeciesNet locally (`make setup-ml`, several GB) or on Kaggle | **decided: install** (2026-09-05); MPS with determinism check, CPU fallback | RESULTS.md Phase 0 |
| O-2 | Create the private GitHub repo and push (`Tlappas-23`), then `make protect` | **decided: yes** (2026-09-05); pushed to github.com/Tlappas-23/parkwild; protect failed, see O-7 | SECURITY.md |
| O-3 | Enable the Cloudflare Access read gate at launch | **decided: public** (2026-09-05), with the species suppression list (config/suppression.toml) | ADR-0008 |
| O-4 | Ingest eBird (421,940 Yellowstone records) | **decided: skip** (2026-09-05); revisit only for checklists with GPS tracks | ADR-0011 |
| O-5 | Quaternius pack license: CC0 (pack page) vs QAL v1.0 (site license page) | **decided: QAL, credit anyway** (2026-09-05); license archived + hashed | docs/3d-assets.md |
| O-6 | Start the app skeleton (React + Vite + MapLibre + R3F; `npm install` is several hundred MB) | **decided: yes** (2026-09-05) | BUILD_SPEC.md Phase 5 |
| O-7 | Repo visibility: GitHub only protects `main` server-side on public or paid repos. Make it public (protection on, code visible, no secrets in it) or stay private with the local pre-push guard only | **decided: public** (2026-09-05); `main` protected server-side, local guard kept | SECURITY.md |
