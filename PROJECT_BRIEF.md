# Project: Wildlife Detection Pipeline from Open Street-Level Imagery

_Superseded by BUILD_SPEC.md on 2026-09-05. Kept verbatim for history. Working
decisions and deviations are recorded in README.md, not here._

## Objective

Build a pipeline that finds animals in crowdsourced street-level photographs of US
national parks, identifies them to species where possible, and records where and when
each sighting occurred. Output is a queryable spatiotemporal dataset plus a simple map.

## Hard constraints

Read these before planning. They are not negotiable.

1. **Zero cost.** No paid APIs, no cloud compute billing, no services requiring a credit
   card. If a step seems to need paid infrastructure, stop and report rather than
   signing anything up.
2. **Do not use Google Maps, Street View, or Google Maps Platform APIs as an image
   source.** Google's Maps Platform Terms of Service explicitly prohibit creating an
   index of object locations from Street View imagery and prohibit using Maps content to
   train, test, validate, or fine-tune models. This rules the source out entirely. Do not
   propose workarounds, unofficial endpoints, or scraping the web viewer.
3. **Respect obscured coordinates.** iNaturalist and GBIF deliberately fuzz locations for
   threatened and poaching-sensitive species. Never attempt to de-obscure them. Filter
   these records out of precision-sensitive analysis rather than working around the
   obscuring.
4. **Attribution.** Mapillary imagery is CC BY-SA 4.0. Any stored record or published
   output must carry image ID, contributor username, and license.

## Stack — already decided, do not re-litigate

| Concern | Choice |
|---|---|
| Imagery + metadata | Mapillary API (free access token) |
| Park boundaries | NPS boundary shapefiles, or OSM relations via Overpass |
| Road & trail geometry | Overpass API |
| Animal detection | MegaDetector |
| Species classification | SpeciesNet (`pip install speciesnet`, Apache 2.0) |
| Validation ground truth | iNaturalist API (no key required) |
| Storage & spatial queries | DuckDB + spatial extension |
| Map output | MapLibre GL JS + OSM raster tiles |
| GPU, if needed | Kaggle notebooks (30 free GPU hrs/week) or local CPU |

If you believe one of these is wrong, say so in your Phase 0 report — do not silently
substitute something else.

---

## Phase 0 — Feasibility gate (do this first, then STOP)

The whole project hinges on an unknown: what fraction of street-level frames in a park
actually contain a detectable animal, and are the detections real? Measure this before
building anything else.

**Steps**

1. Get a Mapillary client access token (free registration).
2. Pick one high-wildlife corridor with known Mapillary coverage. Suggested candidates,
   in order: Lamar Valley (Yellowstone), Moose-Wilson Road (Grand Teton), Cades Cove
   (Great Smoky Mountains). Verify coverage exists before committing to one.
3. Query the Mapillary Graph API for images in that area. Note: as of January 2026,
   bbox queries against `/images` must be **smaller than 0.01 degrees square**, so tile
   your search region into a grid of sub-boxes and paginate. Verify this constraint
   against current docs — it may have changed.
4. Pull metadata for 300–500 images. Capture at minimum: image ID, lat/lng, `captured_at`
   (epoch milliseconds), compass angle, camera type, contributor, and the highest
   available thumbnail URL. Confirm exact field names against the live API rather than
   assuming.
5. Download the images at the largest resolution available (2048px or original — not a
   small thumbnail; resolution is the binding constraint on detection range).
6. Run SpeciesNet's full ensemble over them. Use its geographic filter with ISO code
   `USA` to suppress species that don't occur in North America.

**Report these five numbers and stop:**

- What fraction of images produced any MegaDetector animal detection above 0.2 confidence
- Of those, what fraction are real animals on manual inspection of ~30 samples (be honest;
  expect rocks, shrubs, and logs)
- Estimated distance of true positives from the camera, and the apparent range beyond
  which detection fails
- Species-level agreement rate against your own eyes on the true positives
- Mapillary image density in the test corridor (images per km, and date range covered)

Then wait for a decision before proceeding. If the true-positive rate is under ~2% or the
boxes are mostly vegetation, say so plainly — a negative result here is a useful outcome,
not a failure to work around.

---

## Phase 1 — Ingest

Only after Phase 0 is approved.

- Build a park-scoped index: given a park name, resolve its boundary, pull road and trail
  geometry inside it, tile the bbox to respect the query size limit, and enumerate all
  Mapillary images with their metadata.
- Persist to DuckDB. One row per image, deduplicated by image ID.
- Make it resumable. Long crawls will be interrupted; store progress per tile so a rerun
  picks up where it left off rather than restarting.
- Rate-limit politely and back off on 429s.

## Phase 2 — Detection

- Batch images through the MegaDetector + SpeciesNet ensemble.
- Store every detection: bounding box, detection confidence, top-5 species labels with
  scores, and the taxonomic rollup SpeciesNet produces for low-confidence predictions.
- **Keep raw model output separate from any filtered or adjudicated view.** Do not
  overwrite predictions with corrections; write corrections to a separate table so
  accuracy can be recomputed later.
- Cache aggressively. Never re-run inference on an image already processed.

## Phase 3 — Position estimation

An image tells you where the *camera* was, not where the *animal* was.

- Start with the naive version: record the camera position and compass angle, and treat
  the sighting as a bearing from a point.
- Then estimate range using a ground-plane assumption plus a body-size prior for the
  predicted species, combined with the bounding box height and camera field of view.
- **Report uncertainty explicitly.** Expect tens of meters of error. Aggregate to H3 cells
  rather than presenting false-precision point coordinates.

## Phase 4 — Validation

This is what separates a demo from something defensible.

- Pull iNaturalist research-grade observations for the same park, same species, same month
  as your detections.
- Compare distributions: do your detections agree with independent human observations on
  which species are present, in what relative abundance, and in which seasons?
- Report precision and recall where you can establish them, and be explicit about where
  you cannot.
- Expect and quantify road bias — street-level imagery oversamples animals near roads.
  State this as a limitation rather than burying it.

## Phase 5 — Output

- DuckDB file with the full dataset.
- A CSV export with attribution columns intact.
- A single-page MapLibre map: H3 cells colored by detection count, filterable by species
  and by date range, popups linking back to the source Mapillary image.

---

## Known pitfalls — address these, don't discover them

- **Domain shift is the main risk.** MegaDetector and SpeciesNet were trained on camera
  trap imagery: animal close to the lens, filling much of the frame, camera at animal
  height. Street-level imagery is a distant sideways landscape view. Published benchmark
  accuracy will not transfer. Measure on your own data.
- **Small objects.** Detection quality collapses with distance. Consider tiled inference
  over image crops if whole-image detection underperforms, but measure the cost/benefit.
- **Base rate.** Most frames are empty road. Design for a low hit rate.
- **Coverage is uneven.** Mapillary depends on contributors. Some parks have rich
  coverage, some have almost none. Check before promising a park.
- **Seasonal bias.** People upload in summer. Your temporal distribution reflects tourism
  patterns, not animal presence.

## Working style

- Ask before installing anything large or restructuring the project layout.
- Commit at the end of each phase with a message describing what was verified, not just
  what was written.
- Write the accuracy numbers into a `RESULTS.md` as you go. If the pipeline doesn't work
  well, that file should say so.
- Prefer boring, deterministic batch code. Do not build an agent loop for work that a
  `for` loop does better. Reserve LLM calls for genuinely ambiguous species
  adjudication, and mark those predictions as lower-confidence than model output.
