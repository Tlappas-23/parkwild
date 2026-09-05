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

## Open questions with a planned experiment

- **Q-1 SpeciesNet determinism on MPS.** Run 20 images twice; predictions must be byte-identical. If not, force CPU and record the backend in `runs`. (Decision 1 condition.)
- **Q-2 Panorama slices vs whole panoramas.** Ablation: same 100 panoramas whole and sliced; compare animal-box rate and review precision.
- **Q-3 Country filter on/off.** Same frames with and without `--country USA`; count label changes.
- **Q-4 Mapillary's own `animal--ground-animal` tags as a pre-filter.** Fetch with `pull --with-mapillary-detections`; overlap with MegaDetector boxes >= 0.2.
- **Q-5 Trivial baseline.** Predict the most common reviewed species for every true positive; compare with SpeciesNet's species agreement.
