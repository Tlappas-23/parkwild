# parkwild

Find animals in crowdsourced street-level photos of US national parks, identify
them to species where the model can, and record where and when. The output is a
queryable DuckDB dataset plus a map. Side project; zero budget; honest numbers.

The full brief is in [PROJECT_BRIEF.md](PROJECT_BRIEF.md). Accuracy numbers, good
or bad, go in [RESULTS.md](RESULTS.md).

The build now follows [BUILD_SPEC.md](BUILD_SPEC.md): three decoupled tracks,
Phase 0 routes instead of gating, and the app ships on reference data whatever
detection turns out to be worth. Choices are logged in [DECISIONS.md](DECISIONS.md);
the security model is in [SECURITY.md](SECURITY.md).

**Status (2026-09-05):** Phase 0 read on both populations and routed:
Track B is a supplementary layer (ADR-0013). Phase 1 done: 59,805 Yellowstone
sightings exported. Phase 2 running at supplementary scope on Lamar Valley.
The app renders the real export and deploys to GitHub Pages from `main`:
https://tlappas-23.github.io/parkwild/ (first deploy on the next merge).
See RESULTS.md for numbers, DECISIONS.md for why.

## Hard constraints

1. **Zero cost.** No paid APIs, no cloud billing, nothing that wants a card.
2. **No Google Maps / Street View.** Their terms forbid indexing object locations
   from Street View and using Maps content for models. Not used, not worked around.
3. **Respect obscured coordinates.** iNaturalist/GBIF fuzz sensitive species.
   Those records get filtered out of precision-sensitive analysis, never de-obscured.
4. **Attribution.** Every stored image row carries `image_id`, `creator_username`,
   `license` (CC BY-SA 4.0) and `source_url`. Anything published also needs the
   Mapillary logo and a link back (Mapillary terms, section 11).

## Stack

| Concern | Choice |
|---|---|
| Imagery + metadata | Mapillary Graph API v4 (free client token) |
| Park boundaries | NPS shapefiles or OSM relations via Overpass (Phase 1) |
| Road & trail geometry | Overpass API |
| Animal detection | MegaDetector (bundled inside SpeciesNet) |
| Species classification | SpeciesNet 5.x, Apache 2.0 |
| Validation ground truth | iNaturalist API (Phase 4) |
| Storage & spatial queries | DuckDB (+ spatial extension from Phase 3) |
| Map output | MapLibre GL JS + OSM raster tiles (Phase 5) |
| Compute | local M2 Pro (PyTorch MPS) or Kaggle free GPU |

Nothing in the stack was substituted. See "Verified against live docs" below
for the two API details that shaped the crawler.

## Tracks

| Track | What | Where |
|---|---|---|
| A: reference data | iNaturalist + GBIF sightings, deduplicated, exported as H3 cells | `scripts/track_a.py`, `parkwild/{inaturalist,gbif,sightings,export}.py` |
| B: detection | Mapillary crawl, SpeciesNet, Phase 0 numbers per population | `scripts/phase0.py`, `parkwild/{mapillary,download,pano,speciesnet_runner,review,report}.py` |
| C: app | React + MapLibre + R3F, static files, no backend | `app/` (Phase 5, not started) |

Both A and B write the same `sightings` schema with `source` and
`confidence_basis`; the app reads only that.

## Layout

```
.
├── PROJECT_BRIEF.md          the brief, verbatim
├── RESULTS.md                the numbers ledger (auto-blocks + hand-written verdicts)
├── README.md                 this file
├── BUILD_SPEC.md             the full build spec (supersedes the brief)
├── DECISIONS.md              ADRs + the open-decisions table
├── SECURITY.md               threat model and controls
├── docs/
│   ├── finetuning-decision.md   when (and when not) to fine-tune, and how to test it
│   └── 3d-assets.md             Phase 6 sourcing sheet: species, candidates, license status
├── config/parks.toml         parks: iNaturalist place id, bbox, corridors
├── config/
│   └── corridors.toml        candidate corridors: bbox, state, notes
├── src/parkwild/             the library (pure batch code, no agents)
│   ├── geo.py                bbox tiling under Mapillary's 0.01 deg^2 limit, haversine
│   ├── config.py             paths, .env token, corridor loader
│   ├── mapillary.py          Graph API client: throttle, backoff, tile-splitting crawl
│   ├── overpass.py           road/trail km inside a bbox
│   ├── storage.py            DuckDB schema + upserts
│   ├── download.py           full-res image fetch with URL refresh + verification
│   ├── speciesnet_runner.py  run SpeciesNet as a subprocess, parse its JSON
│   ├── review.py             manual-inspection gallery + CSV
│   └── report.py             the five Phase 0 numbers -> RESULTS.md
│   ├── pano.py               equirectangular -> 4 horizon windows (fixes framing, not resolution)
│   ├── inaturalist.py        iNat API v1 client + normaliser (obscured coords flagged, never recovered)
│   ├── gbif.py               GBIF occurrence client + normaliser (iNat mirror skipped by dataset key)
│   ├── sightings.py          Track A ingest orchestration + cross-source dedupe
│   ├── export.py             cells.geojson (H3 r9), species.json, sightings.parquet, manifest.json
│   ├── contracts.py          stage-boundary assertions (lon/lat, bbox, epoch units, conservation)
│   └── decisionlog.py        reports/decision_log.jsonl writer
├── scripts/phase0.py         Track B CLI: coverage | pull | download | slice | detect | sample | report
├── scripts/track_a.py        Track A CLI: places | ingest | dedupe | export | summary | all
├── scripts/smoke.py          end-to-end on fixtures, no network (CI, < 5 min)
├── scripts/check_secrets.py  pre-commit + CI secret scan
├── scripts/github_protect.sh branch protection for main via gh api
├── notebooks/phase0_inspection.ipynb   narrative walkthrough of the manual review
├── tests/                    offline tests (in-memory DuckDB, fake API client)
├── data/                     gitignored: images, DuckDB file, model JSON, review galleries
│   └── review/<corridor>/review.csv    tracked: my hand-entered verdicts
├── Makefile                  setup / setup-ml / test / phase0 targets
├── requirements.txt          light deps (no torch)
└── requirements-ml.txt       speciesnet (torch, yolov5, weights)
```

## Setup

```bash
make setup            # .venv from Anaconda's Python 3.12, light deps, editable install, Jupyter kernel
make hooks            # pre-commit secret scan for this clone
cp .env.example .env  # paste MAPILLARY_TOKEN from https://www.mapillary.com/dashboard/developers
make test lint smoke  # offline; no token or model needed
make setup-ml         # PyTorch + SpeciesNet. Several GB. Only when ready.
make track-a PARK=yellowstone   # iNaturalist + GBIF -> DuckDB -> data/export/yellowstone/
```

Why Anaconda's 3.12 and not Homebrew's 3.14: SpeciesNet declares
`requires-python < 3.15` and pins `yolov5`, whose wheels lag new Python releases.
3.12 is the safe choice on Apple silicon.

## Phase 0 runbook

Run in order. Every step is idempotent and resumable.

| Step | Command | What it does | Output |
|---|---|---|---|
| 1 | `make coverage` | Counts images, sequences and date range in each candidate corridor using the cheapest fields. Picks nothing; tells me where the imagery is. | `data/coverage_<date>.json` |
| 2 | `make pull CORRIDOR=lamar_valley` | Tiles the bbox, walks every tile, stores one row per image. Tiles that hit the 2000 cap get quartered. Progress per tile, so a rerun resumes. | `images`, `tiles` tables |
| 3 | `make download CORRIDOR=...` | Picks 400 perspective frames spread across sequences (max 20 each), downloads the original resolution, verifies each file. `--population pano --limit 100` does the same for panoramas. | `data/images/<corridor>/`, `data/images/<corridor>_pano/`, `downloads` table |
| 3b | `make slice CORRIDOR=...` | Cuts each downloaded panorama into four 90-degree horizon windows. Fixes framing, not resolution. | `data/images/<corridor>_pano_slices/` |
| 4 | `make detect CORRIDOR=... POPULATION=perspective\|pano` | Runs the full SpeciesNet ensemble with `--country USA --admin1_region <state>` on CPU (MPS segfaults here, E-012), records the run and its backend, parses the JSON into the append-only raw tables. | `data/predictions/<corridor>_<population>.json`, `runs`, `predictions_raw`, `detections_raw` |
| 5 | `make sample CORRIDOR=... POPULATION=...` | Stratified sample of 30 animal boxes across three confidence bands, one per frame, drawn and cropped, plus `review.csv`. | `data/review/<corridor>/<population>/` |
| 6 | fill `review.csv` (or use the notebook) | `verdict` tp/fp/unsure, `true_species`, `species_agree` yes/rollup/no/na, `est_distance_m`. | |
| 7 | `make report CORRIDOR=... POPULATION=...` | Imports the verdicts, asks Overpass for road km, computes the numbers with Wilson intervals and cluster counts, writes them into `RESULTS.md`. Recall is printed as unmeasured. | `RESULTS.md`, `data/phase0_<corridor>_<population>.json` |

Then route per BUILD_SPEC.md and record the routing in `DECISIONS.md`. Track A
and the app do not wait for this.

## Track A runbook

```bash
make track-a PARK=yellowstone          # ingest iNaturalist + GBIF, dedupe, export, summary
.venv/bin/python scripts/track_a.py ingest --park yellowstone --gbif-counts-only   # what GBIF holds, by dataset
.venv/bin/python scripts/track_a.py ingest --park yellowstone --include-ebird      # only after ADR-0011 is decided
.venv/bin/python scripts/track_a.py landmarks --park yellowstone   # park outline + OSM landmarks + tour stops (network, no DB)
.venv/bin/python scripts/track_a.py roads --park yellowstone       # roads.json: OSM roads + trails graph for the route planner (network, no DB)
.venv/bin/python scripts/track_a.py index                          # app/public/data/parks.json: every park, counts, credited hero photo
.venv/bin/python scripts/parks_seed.py                             # look up all 63 parks on iNaturalist -> config/parks.seed.toml
```

### Adding a park

1. `track_a.py places --query "Grand Teton"` for the iNaturalist place id; add
   a `[key]` table to `config/parks.toml` with name, state, place id, bbox and
   an ordered `tour` list (OSM feature names; `tour_fallback` gives a
   coordinate and an `@wiki` article title for stops OSM cannot name).
2. `make track-a PARK=key`, then `track_a.py landmarks --park key` and
   `track_a.py roads --park key`, then `make app-data PARK=key`. The app lists every park whose data folder was
   baked in; `?park=key` opens it directly. Suppression and taxonomy rules
   apply everywhere; the imagery track and bias figures are per corridor.

Outputs land in `data/export/<park>/`: `cells.geojson` (H3 resolution 9, one
feature per cell with a compact species list, open coordinates only,
sensitive species excluded or coarsened per `config/suppression.toml`),
`species.json` (counts, seasonality, obscured share, source mix, suppression
treatment, the other common names a species has carried), `sightings.parquet`
(full canonical records with attribution), `photos_*.json` (licensed
iNaturalist photographs by species and by cell), `landmarks.json` and
`boundary.geojson` (tour stops and the park outline) and `manifest.json`
(SHA-256 per file, git commit, the park's display name). `make bias` adds the road and
seasonal bias block to RESULTS.md. `make app-data` copies the exports into
`app/public/data/<park>/`, where the app compiles the manifest in and refuses
any data file whose hash does not match.

## The app

`app/` is React + Vite + MapLibre + React Three Fiber + Zustand, static files
only. Photographs from iNaturalist observations are the evidence layer
(ADR-0015): card art and hero per species, a "seen here" strip per cell,
each credited to its observer with its licence and a link. `make app` installs, builds and enforces the JS budget (entry chunk
under 200 KB gzipped; the map and 3D libraries are lazy chunks with their own
caps). Pages: a map of the park (OpenFreeMap vector basemap under a hillshade and
3D terrain from the AWS terrain tiles, a USGS imagery toggle, everything
outside the iNaturalist park polygon washed out) with H3 cells, species and
year filters, landmarks, a guided tour that flies stop to stop and lists the
species recorded within 2.5 km of each, a route planner that orders the sites
you tick from your position over the park's own road and trail graph
(ADR-0018), and a cell panel that follows the species filter and links the
same box on iNaturalist; species grid and detail
with month histogram and a lazy 3D viewer; About with methods, limitations,
suppression and licensing; a home page with a card per park (counts, a
credited Commons photograph, ADR-0019) that opens each park's map with an
animated arrival on the whole outline (ADR-0017). Deploy target is
Cloudflare Pages with `app/public/_headers` for CSP.

Rough cost on this machine: steps 1 to 3 are a few minutes of API calls and
about 1 to 2 GB of JPEGs. Step 4 is the slow one: MegaDetector on 400 original
frames is on the order of 15 to 30 minutes on the M2 Pro's GPU via MPS. If that
turns out painful, the same JSON can be produced on a Kaggle notebook and loaded
with `phase0.py detect --parse-only`.

## Verified against live docs (2026-09-05)

Mapillary Graph API, from the developer documentation page:

- bbox searches against `/images` must cover **less than 0.01 deg²**. The
  changelog dates this to January 16, 2026. `geo.tile_bbox` uses 0.05 × 0.05
  deg tiles (0.0025 deg², a 4× margin).
- **Pagination only works together with `creator_username`.** A plain bbox
  search returns at most 2000 rows and there is no page two. So a tile that
  comes back with exactly 2000 rows is quartered and re-queried; that is what
  `MapillaryClient.crawl` does, down to a 0.002 deg floor.
- Field names used: `id, geometry, computed_geometry, captured_at (ms epoch),
  compass_angle, computed_compass_angle, camera_type, is_pano, make, model,
  width, height, quality_score, sequence, creator{id,username},
  thumb_1024_url, thumb_2048_url, thumb_original_url`.
- Auth: `Authorization: OAuth <token>` header. Search rate limit 10,000/min
  per app; the client sleeps 150 ms between calls anyway and backs off on 429.

Two behaviours that are **not** in the docs, measured on 2026-09-05:

- **The 2000 cap is fuzzy.** Lamar Valley tiles that returned 1879 to 1973
  rows were truncated (their quarters summed to 2500 to 3400), while tiles at
  1849 and below were complete. The crawler treats any tile returning 1500 or
  more rows as capped and splits it.
- **Dense tiles return HTTP 500**, not a truncated list. Two 0.05 deg tiles in
  Cades Cove errored at any `limit`, and their quarters answered normally. The
  crawler treats a repeated 5xx on a splittable tile as "too heavy" and splits
  it; only a tile at the minimum size is recorded as an error and retried on
  the next run.
- License: CC BY-SA 4.0 (terms section 3b); logo + link back on published
  output (section 11).

SpeciesNet, from the `google/cameratrapai` repository at version 5.0.5:

- CLI: `python -m speciesnet.scripts.run_model --folders ... --predictions_json
  ... --country USA --admin1_region WY --batch_size 8 --bypass_prompts`.
  Re-running with an existing `--predictions_json` resumes automatically.
- Device selection is `cuda`, then `mps`, then `cpu`, so Apple silicon is used.
- The detector returns every box down to 0.01 confidence; thresholding is
  mine, at query time.
- Its loader applies the EXIF orientation tag (`ImageOps.exif_transpose`)
  before inference, so box coordinates refer to the upright image. 13 of the
  400 Lamar frames carry a 180-degree tag; the review renderer applies the
  same transpose so the boxes I inspect sit where the model put them.
- Output per image: `classifications{classes[5], scores[5]}`, `detections[{category
  '1'|'2'|'3', label, conf, bbox[x_min,y_min,w,h] normalised}]`, `prediction`,
  `prediction_score`, `prediction_source`, `model_version`.

Overpass, measured the same day: the main instance answers HTTP 406 to
python-requests' default User-Agent and 200 to the same query with a named
one. The client sends `parkwild/<version>` and tries the lz4 mirror first.

One optional addition, not a substitution: `phase0.py pull --with-mapillary-detections`
also stores Mapillary's own segmentation labels (`detections.value`, e.g.
`animal--ground-animal`). It is a free, in-domain pre-filter worth measuring
against MegaDetector, and it costs one extra field in the query.

## How the code is written (the narrative standard)

Every module opens with what problem it solves, what was tried first, why
that failed, what it does now, and what is unresolved. Every constant carries
a provenance tag (`MEASURED`, `DERIVED`, `BORROWED`, `ASSUMED`, `ARBITRARY`)
and says what would change it; `scripts/provenance_report.py --strict` runs
in CI and fails on an untagged one. Replaced methods stay in the code as
`_v1` with a docstring giving the evidence and a test that reproduces the
comparison (`is_capped_v1`, `images_pending_download_v1`,
`cluster_detections_v1`, `pick_sample_uniform_v1`). Every filter logs rows
in and out to `reports/decision_log.jsonl`, and every script ends with a
decision summary. Samples are pinned in `reports/samples/*.json` with their
seeds. `EXPERIMENTS.md` is the ledger, failures included; `DECISIONS.md` the
ADRs; `docs/data-cards/` one page per source.

## Data model (DuckDB)

| Table | Key | Purpose |
|---|---|---|
| `images` | `image_id` | crawl index with attribution columns, both raw and SfM positions, thumbnail URLs, raw JSON |
| `tiles` | `tile_id` | crawl progress: done / split / capped |
| `downloads` | `image_id` | local path, size kind, dimensions, sha256, or the error |
| `predictions_raw` | `(image_id, model_version)` | SpeciesNet's ensemble output, untouched |
| `detections_raw` | `(image_id, model_version, det_idx)` | every box, untouched |
| `manual_review` | `(image_id, det_idx, reviewer)` | my verdicts; the only table humans write |

Raw model tables are never updated by corrections. Accuracy is always a join
between `*_raw` and `manual_review`, so it can be recomputed later or against a
different model version.

## Working rules

- Ask before installing anything large or restructuring the layout.
- Commit at the end of each phase; the message says what was verified.
- Numbers go in `RESULTS.md` as they are produced, including bad ones.
- Boring batch code. No agent loops. LLM calls only for genuinely ambiguous
  species adjudication, and those get marked lower-confidence than model output.
