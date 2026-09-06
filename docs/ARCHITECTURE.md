# parkwild: architecture

Static site, no server, no accounts, zero cost. A Python pipeline bakes one
folder of data per park; a React app reads those folders; GitHub Pages
serves everything. This page is the map of the system. `docs/USER-GUIDE.md`
is how to use the site; `DECISIONS.md` and `EXPERIMENTS.md` are why it is the
way it is.

```
 sources (all free, no keys in the page)            pipeline (Python, DuckDB)                 per-park data (static JSON)          app (React + MapLibre)
 ─────────────────────────────────────────          ────────────────────────────              ─────────────────────────────        ───────────────────────────
 iNaturalist API  ── research-grade obs ──┐         track_a.py ingest ─► sightings ─┐         cells.geojson   species.json          Home  · every park, one map
 GBIF API         ── other datasets ──────┤──────►  track_a.py dedupe                ├──────►  photos_*.json   sightings.parquet     Map   · cells, tour, places,
 Mapillary API    ── street imagery ──┐   │         phase0.py / track_b.py (CPU CV) ─┘         camera_pass.json                        planner, All parks
 SpeciesNet       ── detector+classifier ─┘         track_a.py landmarks (OSM, Wikipedia,      landmarks.json  boundary.geojson      Species · photos, seasons
 OpenStreetMap    ── Overpass ────────────────────►   Commons, Mapillary)  ─────────────────►  roads.json      amenities.json        Ask   · on-device models, opt-in
 Wikipedia / Commons ── text, photos, licences       track_a.py roads · amenities · index      manifest.json (SHA-256 of each)      About · per-park honesty page
 USGS / AWS terrain / OpenFreeMap ── tiles (runtime only) ─────────────────────────────────────────────────────────────────────────► basemap, imagery, 3D terrain
```

## Three tracks

| Track | What | Where | Depends on |
|---|---|---|---|
| A · reference data | Human sightings: iNaturalist research grade + GBIF datasets, deduplicated, normalised (names, subspecies), suppression for sensitive species, H3 cells, photographs with licences | `src/parkwild/{inaturalist,gbif,sightings,export,photos,config}.py` | nothing |
| B · detection | Street-level imagery (Mapillary) scored by SpeciesNet on CPU; reviewed by a person; sightings written only above measured thresholds; presented as a separate amber layer | `src/parkwild/{mapillary,download,pano,speciesnet_runner,review,report,trackb,trackb_export,bias}.py`, `scripts/phase0.py`, `scripts/track_b.py` | Track A's park definition; a human review |
| C · app | Reads the baked files; every feature is client-side | `app/src` | Tracks A and B outputs |

Track B never blocks the app: a park with no imagery pass simply has no amber cells and says so on its About page.

## Pipeline commands (per park)

| Command | Reads | Writes | Network | Database |
|---|---|---|---|---|
| `track_a.py ingest --park K` | iNaturalist, GBIF | `sightings` table | yes | write |
| `track_a.py dedupe --park K` | `sightings` | `duplicate_of` | no | write |
| `track_a.py export --park K` | `sightings`, raw iNat JSON | cells, species, photos, parquet, camera_pass, manifest | no | read |
| `track_a.py landmarks --park K` | iNaturalist place, Overpass, Wikipedia, Commons, Mapillary | boundary, landmarks, manifest | yes | none |
| `track_a.py roads --park K` | Overpass | roads.json, manifest | yes | none |
| `track_a.py amenities --park K` | Overpass, roads.json | amenities.json, manifest | yes | none |
| `track_a.py index` | parks.toml, seed, exports, Wikipedia, Commons | `app/public/data/parks.json` | yes | none |
| `phase0.py pull / download / detect --corridor C` | Mapillary, SpeciesNet | images, downloads, predictions | yes | write |
| `phase0.py sample / report`, `species-sample / species-report` | predictions, review CSVs | review galleries, numbers | no | write |
| `track_b.py sightings --corridor C --park K` | predictions | `sightings` (source `mapillary_cv`) | no | write |
| `make app-data PARK=K` | `data/export/K` | `app/public/data/K` | no | none |

DuckDB (`data/parkwild.duckdb`, gitignored) allows one writer at a time, so ingests and detection runs are serialised; the landmark, road, amenity and index steps do not touch it and can run alongside.

## Per-park data files

All files live in `app/public/data/<park>/` and are listed, with a SHA-256, in that park's `manifest.json`. The manifests are compiled into the app; a file whose hash does not match is refused (E-023/E-027 for how that recovers after a deploy).

| File | Contents | Loaded |
|---|---|---|
| `cells.geojson` | One feature per H3 cell (res 9, about 170 m; res 6 for coarsened species) with a compact per-species array `[species_index, count, human_verified, model_predicted, first_year, last_year]` and a shared species index | with the park |
| `species.json` | Per species: counts by source and confidence basis, first/last date, months, other common names, suppression, 3D model credit if any | with the park |
| `photos_species.json`, `photos_cells.json` | Licensed iNaturalist photographs, by species (up to 8) and by cell (top 3 plus one per species); id, host, observer, licence, observation, date, cell | species with the park; cells on first tap |
| `landmarks.json`, `boundary.geojson` | OSM landmarks with Wikidata links, the ordered tour with Wikipedia summaries, near-stop Commons photographs and Mapillary look-around ids; the iNaturalist park polygon | with the park |
| `roads.json` | Roads and trails as a graph: nodes, edges with length, kind, one-way flag, name, geometry | on first route or trail |
| `amenities.json` | Campsites, lodging, trailheads, viewpoints, picnic sites, visitor centres, boat launches, named features; named trails summed from the graph | with the park |
| `camera_pass.json` | Per corridor: frames scored, detections, sightings, named species, imagery months, Phase 0 precision with interval | with the park |
| `bias.json` | Road and seasonal bias of a corridor's imagery against the park's sightings | with the park (Yellowstone only so far) |
| `sightings.parquet` | Every canonical record with attribution, for anyone who wants the table | never by the app |

`app/public/data/parks.json` is the park index (all 63 parks, status, counts, bounding box, credited hero photograph), compiled into the bundle.

## The app

`app/src` is React 19 + Vite 7 + MapLibre GL 5 + Zustand, with lazy chunks for the map, the 3D viewer and the two on-device models.

| Module | Role |
|---|---|
| `store.ts` | One store: park, page, loaded files, filters, selection, tour state, planner state, panel state. `filteredFeatures` is the single definition of "filtered". |
| `data.ts` | Fetch with integrity check against the baked manifest; the self-heal after a deploy; park list from baked manifests |
| `pages/HomePage.tsx`, `HomeMap.tsx` | Park cards with credited photographs, the country map with every park |
| `pages/MapPage.tsx` | The park map: OpenFreeMap style, USGS imagery toggle, terrain, park mask and outline, cells, landmarks, corridors, route, places, All parks; the tour camera and orbit |
| `pages/Tour.tsx`, `tour.ts` | The stop card (Wildlife / Things to do / Photos), species and things near a point or along a trail, near-here photographs |
| `pages/PlanPanel.tsx`, `routing.ts` | Start, sites, drive/hike; Dijkstra over `roads.json`; exact visiting order up to nine sites |
| `pages/CellDetail.tsx`, `PlaceDetail.tsx` | The two drawers: a cell (filter-aware, verification link) and a place (facts, Wikipedia, animals, Commons photographs) |
| `pages/SpeciesPage.tsx`, `SpeciesDetail.tsx` | Grid and detail: photographs, busiest month and effort-adjusted month, sources, model badge only where a pass ran |
| `pages/AskPage.tsx`, `ai.ts`, `photoId.ts`, `wiki.ts` | Opt-in on-device language model with grounded facts and citations; photo suggestion; runtime Wikipedia/Commons lookups |
| `pages/AboutPage.tsx` | Per-park methods and honesty page |

Map layers, bottom to top: imagery (satellite mode) · hillshade · vector landcover · mask · outline · corridors · cells · route · vector lines and labels · landmarks · things · route stops · focus · parks · location.

## Hosting, security, updates

- GitHub Pages from `main` via `.github/workflows/pages.yml`; CI (`ci.yml`) runs the secret scan, ruff, the provenance check (every constant tagged MEASURED/DERIVED/BORROWED/ASSUMED/ARBITRARY), tests and the smoke run; `main` is protected and only PRs with green CI merge (`scripts/ship.sh`).
- Content-Security-Policy in `index.html` and `public/_headers`: self plus the tile hosts, the two iNaturalist image hosts, Commons, the model hosts; `wasm-unsafe-eval` for the on-device models. No analytics, no cookies, no third-party scripts.
- Service worker (vite-plugin-pwa): the shell is precached; data files are cached by content hash; a new worker takes over at install; the app reloads early or shows a "newer version" pill (E-034).
- Public reads, locked writes: the repository is public so branch protection applies; no token is in the page (Mapillary's is used by the pipeline only).

## Background jobs and the owner's loop

Long runs are shell chains in the session scratchpad (recorded in memory and E-033): ingest batches, then landmarks/roads/export per park, then the imagery pass per corridor, then the species review sample. The owner's recurring jobs: review the sample CSV (`data/review/species/perspective/review_me.csv`), run `phase0.py species-report`, and paste the Ask page's "Measure it" table into `docs/ai-eval.md`.

## Where things stand (2026-09-06)

| Area | State |
|---|---|
| Parks | 11 live, 52 seeded (index and map only) |
| Human sightings | 289,000 across the eleven parks |
| Imagery pass | Lamar Valley scored and reviewed (precision 42%, CI 23–64%, n=19); Moose-Wilson and Cades Cove scored, Hayden Valley queued; species review sample pending |
| On-device AI | Shipped opt-in; default model's evaluation pending its first run on the live site |
| Open decisions | O-8 data hosting past ten parks; O-10 sharper imagery with unclear terms |
