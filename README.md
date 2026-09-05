# parkwild

Find animals in crowdsourced street-level photos of US national parks, identify
them to species where the model can, and record where and when. The output is a
queryable DuckDB dataset plus a map. Side project; zero budget; honest numbers.

The full brief is in [PROJECT_BRIEF.md](PROJECT_BRIEF.md). Accuracy numbers, good
or bad, go in [RESULTS.md](RESULTS.md).

**Status (2026-09-05):** Phase 0 code is written and unit-tested offline. It has
not been run against Mapillary yet. Two things are needed first:

1. a Mapillary client token in `.env` (free registration, no card);
2. an OK to run `make setup-ml`, which installs PyTorch + SpeciesNet (several GB).

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

## Layout

```
.
├── PROJECT_BRIEF.md          the brief, verbatim
├── RESULTS.md                the numbers ledger (auto-blocks + hand-written verdicts)
├── README.md                 this file
├── docs/
│   └── finetuning-decision.md   when (and when not) to fine-tune, and how to test it
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
├── scripts/phase0.py         CLI: coverage | pull | download | detect | sample | report
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
cp .env.example .env  # paste MAPILLARY_TOKEN from https://www.mapillary.com/dashboard/developers
make test             # offline tests; no token or model needed
make setup-ml         # PyTorch + SpeciesNet. Several GB. Only when ready.
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
| 3 | `make download CORRIDOR=...` | Picks 400 images spread across sequences (max 20 each, panoramas excluded), downloads the original resolution, verifies each file. | `data/images/<corridor>/*.jpg`, `downloads` table |
| 4 | `make detect CORRIDOR=...` | Runs the full SpeciesNet ensemble with `--country USA --admin1_region <state>`, then parses the JSON into `predictions_raw` / `detections_raw`. | `data/predictions/<corridor>.json` + tables |
| 5 | `make sample CORRIDOR=...` | Picks 30 animal boxes at random (one per frame), draws them, writes `review.csv`. | `data/review/<corridor>/` |
| 6 | fill `review.csv` (or use the notebook) | `verdict` tp/fp/unsure, `true_species`, `species_agree` yes/rollup/no/na, `est_distance_m`. | |
| 7 | `make report CORRIDOR=...` | Imports the verdicts, asks Overpass for road km, computes the five numbers, writes them into `RESULTS.md`. | `RESULTS.md`, `data/phase0_<corridor>.json` |

Then stop, write the decision in `RESULTS.md`, and wait.

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
- License: CC BY-SA 4.0 (terms section 3b); logo + link back on published
  output (section 11).

SpeciesNet, from the `google/cameratrapai` repository at version 5.0.5:

- CLI: `python -m speciesnet.scripts.run_model --folders ... --predictions_json
  ... --country USA --admin1_region WY --batch_size 8 --bypass_prompts`.
  Re-running with an existing `--predictions_json` resumes automatically.
- Device selection is `cuda`, then `mps`, then `cpu`, so Apple silicon is used.
- The detector returns every box down to 0.01 confidence; thresholding is
  mine, at query time.
- Output per image: `classifications{classes[5], scores[5]}`, `detections[{category
  '1'|'2'|'3', label, conf, bbox[x_min,y_min,w,h] normalised}]`, `prediction`,
  `prediction_score`, `prediction_source`, `model_version`.

One optional addition, not a substitution: `phase0.py pull --with-mapillary-detections`
also stores Mapillary's own segmentation labels (`detections.value`, e.g.
`animal--ground-animal`). It is a free, in-domain pre-filter worth measuring
against MegaDetector, and it costs one extra field in the query.

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
