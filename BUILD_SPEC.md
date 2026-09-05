# parkwild — Complete Build Specification

_Received 2026-09-05. Supersedes PROJECT_BRIEF.md (kept for history). One
addition from the same message, recorded here because it is not in the spec
body: "I want authentication for web and app, tight security so no one can
write over what I build." How that is reconciled with the spec's "no auth,
publicly reachable" is in SECURITY.md and DECISIONS.md (ADR-0008)._

End-to-end spec, Phase 0 through shipped application. Supersedes the Phase 0-only
brief. Zero budget throughout.

---

## Definition of done

A deployed, publicly reachable web application that shows where and when animals
have been observed in a US national park, with 3D-rendered species, backed by a
reproducible data pipeline, honest about its own uncertainty, and correctly
attributed.

Not done until all of:

1. App is live at a URL, loads in under 3 s on a mid-range phone, works offline
   after first load
2. Data pipeline runs end to end from a clean checkout with one command
3. Every displayed figure traces to a source record with attribution
4. `RESULTS.md` documents what worked, what didn't, and what remains unmeasured
5. Test suite passes; smoke test exercises the full path in under 5 minutes

---

## Architecture: three decoupled tracks

The single most important structural decision in this project. **Do not couple
these.**

```
Track A — Reference data          Track B — Detection pipeline
iNaturalist + GBIF ingest         Mapillary crawl → SpeciesNet
Known to work. Ships week one.    Unproven. May not pan out.
         │                                    │
         └────────────┬───────────────────────┘
                      ▼
              sightings schema
           (one shape, many sources)
                      │
                      ▼
        Track C — Application layer
     Map + species detail + 3D rendering
   Depends on the schema, not on either source
```

Track A guarantees the app has real data regardless of what Track B produces.
Track C can be built in parallel with both. Every sighting row carries a `source`
column (`inaturalist`, `gbif`, `mapillary_cv`) and a `confidence_basis`
(`human_verified`, `model_predicted`), and the UI renders them differently.

Consequence: **Phase 0 no longer halts the project.** It routes it.

---

## Phase 0 — Feasibility (routing, not gating)

Complete as specified in the prior brief, including:

- Both populations (perspective frames and sliced panoramas), reported separately
- Stratified review sampling across three confidence bands — not top-N by
  confidence, which inflates precision
- Distinct-cluster count alongside raw box count, since consecutive frames from
  one sequence see the same animal
- No recall figure

**Then route on the result:**

| Outcome | Track B becomes |
|---|---|
| Precision ≥ 60%, hit rate ≥ 5% | A primary data source. Full crawl in Phase 2. |
| Precision 35–60%, or hit rate 2–5% | A supplementary layer. Crawl only best-coverage corridors. Surface in UI as model-predicted, visually distinct. |
| Below that | A documented negative result. Write it up properly in `RESULTS.md`, ship the app on Track A, keep the code. |

In all three cases the project continues. Write the routing decision into
`DECISIONS.md` with the numbers that drove it.

---

## Phase 1 — Track A: reference data (start immediately, parallel with Phase 0)

Do not wait on detection. This is the data that guarantees a shippable app.

- iNaturalist API ingest for target parks. Research-grade, Mammalia and Aves,
  full date range. No key required.
- GBIF as a second source for records iNaturalist lacks.
- Normalize both into the `sightings` schema with `source` set appropriately.
- **Respect obscured coordinates.** Both services fuzz locations for threatened
  and poaching-sensitive taxa. Flag them, exclude from precision-dependent
  views, never attempt to recover true positions.
- Deduplicate across sources on observer, time, and location proximity — GBIF
  mirrors a lot of iNaturalist.

Acceptance: a park's worth of real sightings in DuckDB, exported to the same
GeoJSON shape the app will consume. At this point the app has data even if
everything else fails.

## Phase 2 — Track B: detection at scale

Conditional on Phase 0 routing. Scope to what the routing decision allows.

- Resumable crawl, checkpointed per tile. An interrupted run loses one tile.
- Inference batched, cached by image ID, never recomputed.
- Raw predictions append-only. Human corrections go to a separate table. Never
  overwrite model output — accuracy must be recomputable after a model change.
- Run metadata recorded per batch: model version, backend, thresholds, date.

## Phase 3 — Deduplication, validation, bias

- Cluster consecutive-frame detections of the same individual (same sequence,
  same species, within a time and distance window). Report the duplicate rate.
- Validate Track B against Track A distributionally: do the species you detect,
  in the proportions you detect them, resemble independent human observations
  from the same place and season?
- **Quantify road bias explicitly.** What fraction of independent observations
  fall outside imagery coverage? That fraction is invisible to your method by
  construction, and it goes in the UI, not just the docs.
- Quantify seasonal bias. Contributor uploads cluster in summer.

## Phase 4 — Positions and export

- Range estimation from bounding box **height** with a shoulder-height prior.
  Height is far more invariant to viewing angle than width — a bison facing the
  camera presents ~0.8 m of shoulder, not 3 m of body.
- Branch the angular math on camera type: linear mapping for equirectangular
  panoramas, `atan` projection for perspective frames.
- Every position carries an uncertainty interval. Aggregate to H3 resolution 9
  (~170 m edge), comparable to the error magnitude.
- Export artifacts the app consumes:
  - `cells.geojson` — aggregated, per species, with counts and date ranges
  - `species.json` — per-species metadata, seasonal histogram, model reference
  - `sightings.parquet` — full records with attribution, for anyone checking work
  - All pre-baked and static. No backend server, no database in production.

## Phase 5 — Application

**Stack:** React + Vite, MapLibre GL JS, React Three Fiber, Zustand for state,
deployed to Cloudflare Pages or GitHub Pages. All free tier.

Data is static files fetched from the same origin. No API, no auth, no runtime
cost. This is what makes "zero budget" survive contact with real traffic.

**Screens:**

1. **Map.** H3 cells over an OSM or Protomaps basemap. Cells styled soft and
   low-opacity — deliberately probabilistic, never crisp points. Species filter,
   date-range scrubber, cell tap opens detail.
2. **Cell detail.** What was seen here, when, how often, from what source. Source
   badges distinguish human-verified from model-predicted. Links to originating
   images with attribution.
3. **Species browser.** Grid of species. This is where the 3D lives.
4. **Species detail.** Interactive 3D model, seasonal activity chart, range map,
   observation count, confidence basis.
5. **About.** Methods, limitations, licensing, and the road-bias and
   seasonal-bias figures stated plainly. This page is not optional.

**Critical UI rule:** never place a crisp 3D animal at a precise map coordinate.
Positional error is tens of metres; a sharp model at an exact point is a visual
claim of accuracy the data does not support. The map shows aggregated cells. The
3D lives in the detail views, where it is earned.

## Phase 6 — 3D layer

**Start sourcing models during Phase 1, not here.** It is a long-lead item and
the only part of this project with a hard external dependency.

- **Sources:** Poly Pizza, Quaternius, Sketchfab filtered to CC0. These are
  stylized and low-poly. Photoreal rigged animals cost $30–200 each and are out
  of budget. Stylized is the better call anyway: it reads clearly at small sizes,
  ages well, and avoids uncanny valley.
- **Apple's assets are not available.** The AR Quick Look gallery, the Apple TV
  wildlife screensavers, Maps' rendered models — all proprietary, first-party
  licensed. There is no version of this where you obtain them. The look you want
  comes from rendering discipline, not from their models.
- **Pipeline:** glTF, Draco-compressed, under 2 MB each. Lazy-load per species,
  never bundle all of them. Provide a static render fallback for low-end devices
  and users with reduced-motion set.
- **iOS AR path (optional, high impact):** convert glTF to USDZ and ship an AR
  Quick Look link. On iOS this places the animal in the real landscape natively,
  costs nothing, and is the single most impressive thing this app can do.

**Getting the Apple look — this is rendering, not models:**

- Lighting: soft studio HDRI, single warm key, cool fill, visible contact shadow.
  Contact shadows do more for perceived quality than polygon count.
- Materials: proper PBR roughness. Avoid mirror speculars on fur.
- Camera: slight orbit on idle, spring easing, never linear, 200–400 ms.
- Type: system font stack, tight tracking above 24 px, generous line height.
- Color: one accent, everything else neutral. Resist a second accent.
- Space: more padding than feels necessary.
- Restraint: animate one thing at a time.

## Phase 7 — Ship

- Lighthouse ≥ 90 across the board on mobile.
- Performance budget enforced in CI: initial JS under 200 KB gzipped, first 3D
  model under 2 MB, LCP under 2.5 s on simulated 4G.
- Offline via service worker after first load.
- Accessibility: keyboard navigation, screen-reader labels on map controls,
  respect `prefers-reduced-motion` (disable orbit and transitions), verified
  contrast.
- Attribution page listing every data source, model, and 3D asset with license.
- Reproducibility: `make all` from a clean checkout regenerates every artifact.

---

## Cross-cutting requirements

**Honesty in the product, not just the docs.**
- Recall is never reported. There is no exhaustive annotation; a recall figure
  would be fabricated. Say "unmeasured."
- Precision carries a confidence interval, not a bare percentage.
- Model-predicted and human-verified sightings are visually distinguishable
  everywhere they appear.
- The About page states road bias, seasonal bias, and positional error in plain
  language with numbers.
- Absence of data is never rendered as absence of animals. An empty cell means
  nobody looked.

**Licensing.**
- Mapillary imagery is CC BY-SA 4.0. Attribution is mandatory wherever an image
  is displayed. Be conservative about ShareAlike: extracted coordinates are
  arguably facts rather than derivative works, but if you display or redistribute
  the images themselves, ShareAlike attaches. Get a straight answer before
  publishing images; publishing only derived coordinates plus attribution is the
  safe path.
- 3D models: record license per asset, credit per the terms.
- Google Street View remains excluded. Their terms prohibit indexing object
  locations from Street View imagery and prohibit using Maps content to train or
  validate models.

**Engineering.**
- Logic in `src/`, notebooks and scripts orchestrate. Anything that cannot be
  unit-tested is in the wrong place.
- `DECISIONS.md` in ADR form: context, decision, alternatives rejected,
  consequence. Backfill existing choices.
- Runtime decision log to `reports/decision_log.jsonl` — every filter records how
  many rows went each way and under what rule. When 8,000 rows vanish, the output
  says which threshold ate them.
- Contracts asserted at stage boundaries: coordinate ranges, bbox normalization,
  timestamp units, row-count conservation.
- **Explicit column lists on every insert.** Positional `SELECT *` inserts caused
  a silent latitude/longitude swap in the original scaffold. Never again.
- CI on push: lint, unit tests, smoke test, performance budget.

---

## Sequencing

Phases 1, 5, and 6 start immediately and run in parallel with Phase 0. This is
the point of the three-track architecture — the app is never blocked on the
detection result.

```
Week 1-2    Phase 0 (routing)  ║  Phase 1 (iNat/GBIF)  ║  Phase 6 (model sourcing)
Week 3-4    Phase 2 (per route) ║  Phase 5 (app skeleton on Track A data)
Week 5-6    Phase 3 + 4         ║  Phase 5 (detail views, 3D integration)
Week 7-8    Phase 7 (polish, perf, a11y, deploy)
```

Estimates assume part-time work and will slip. The ordering matters more than the
weeks.

---

## Do not

- Couple the app to the detection pipeline. Track A ships regardless.
- Report a recall number.
- Render model-predicted sightings identically to human-verified ones.
- Place a crisp 3D animal at a precise coordinate.
- Claim panorama slicing extends detection range — it fixes distortion and
  object-to-frame ratio, not resolution. The pixels are the pixels.
- Select review samples by confidence rank.
- Add a paid service, a backend server, or a database in production.
- Quietly drop a population, source, or negative result because it looks bad.

## Stop and ask

- Any spend, at all.
- Phase 0 routing lands ambiguously between bands.
- A 3D asset's license is unclear.
- ShareAlike obligations look like they attach to the published dataset.
- A phase looks like it will take more than double its estimate.

## Reporting

Report at each phase boundary: what was built, what was measured, what was
decided and why, what is now known to be false, and what remains unmeasured.

A phase that produces a clear negative result is a completed phase. Write it
down and route around it.
