# parkwild

A free map of where people have seen wild animals in America's national parks.

Every research-grade observation on iNaturalist and every GBIF record with
its own review, for mammals and birds, gathered park by park, deduplicated,
and drawn as hexagonal cells about 170 m across. On top of that: a virtual
tour of each park's landmarks in 3D, species pages that show where an animal
is seen most across all parks, a route planner over the park's real roads and
trails, and an optional assistant that runs entirely in your browser. No
server, no accounts, no tracking, no paid service anywhere in the chain.

Live site: https://tlappas-23.github.io/parkwild/

## What the site does

- **Parks.** A map of all 63 national parks. Live parks open on click; the
  rest show their status. Eleven are live today and the remaining 52 are
  being added by an unattended pipeline (see Status).
- **Map.** The park outline over relief or USGS imagery, with a 3D option.
  Blue cells are places where people recorded animals; deeper blue means
  more sightings. Tap a cell for its species, years, photographs and a link
  to the same box on iNaturalist. Filter by species and by years.
- **Tour.** Lands close over each landmark in satellite 3D, turns slowly
  while you read, then follows the park's roads to the next stop. Each stop
  lists the wildlife recorded within 2.5 km, things to do, and photographs.
- **Places.** Every named trail, site, campground and facility, ordered by
  how many sightings people recorded within reach, with its busiest months,
  photographs, Wikipedia summary and the animals seen there.
- **Species.** Search one park or all parks at once. Every species page shows
  where people see the animal, park by park, with a button that opens that
  park's map on the animal's busiest cell.
- **Plan a visit.** Your location or any landmark as the start, the places
  you want, drive or hike, and the best order over the real road and trail
  graph, with turn-by-turn links.
- **Ask.** A small language model that answers only from the site's own data
  and cites every number. It downloads once, on request, and runs on your
  device. Until you press Enable, no model is involved anywhere.
- **About.** Per park: what the data is, what it cannot tell you, and where
  a computer-vision pass ran (three roadside corridors in Yellowstone and
  Grand Teton and Great Smoky Mountains) and how well it did.

## What the numbers mean

Sightings are what people reported, not how many animals there are. An empty
cell means nobody looked. Observations cluster on roads, trails and
viewpoints and in summer. Sensitive species keep the coarse or hidden
positions their sources gave them and are never sharpened. Model-predicted
detections from street-level imagery are counted separately from
human-verified records, drawn differently, and only shown where the pass
actually ran. No recall figure is ever published because nobody has counted
every animal. The full reasoning is in [DECISIONS.md](DECISIONS.md) and every
measurement, including the failures, is in [EXPERIMENTS.md](EXPERIMENTS.md).

## How it is built

Three tracks feed one static app.

| Track | What it does | Code |
|---|---|---|
| A, reference data | iNaturalist and GBIF sightings per park into DuckDB, deduplicated across sources, exported as cells, species, photographs; OpenStreetMap landmarks with Wikipedia summaries and Commons photographs; the road and trail graph; things to do | `scripts/track_a.py`, `src/parkwild/{inaturalist,gbif,sightings,export,photos,landmarks,roads,amenities}.py` |
| B, detection | Mapillary street-level imagery on chosen corridors, MegaDetector plus SpeciesNet on CPU, a stratified human review, precision with confidence intervals | `scripts/phase0.py`, `scripts/track_b.py`, `src/parkwild/{mapillary,download,pano,speciesnet_runner,review,report,trackb}.py` |
| C, the app | React, MapLibre GL, Zustand; OpenFreeMap vector tiles, USGS imagery, AWS terrain tiles; WebLLM and Transformers.js for the on-device models; a service worker for offline shell and safe updates | `app/` |

Every park's data is a folder of JSON files under `app/public/data/<park>/`
with a manifest of SHA-256 hashes that is compiled into the app, so a file
swapped on the server is refused. A cross-park species index and the park
index sit beside the folders. Publishing is a data-only pull request that a
script opens from a fresh git worktree, so the working tree is never
touched. `docs/ARCHITECTURE.md` has the full map, file by file.

## Repository layout

```
app/                     the site (Vite, React, MapLibre): src/app (shell), src/pages, src/components, src/lib (pure logic, tested),
                         src/data (loaders, types), src/store, src/styles; scripts/ has the build helpers and the headless tour probe
config/                  parks.toml (all 63 parks), corridors.toml, suppression.toml, taxonomy.toml
docs/                    ARCHITECTURE.md, USER-GUIDE.md, data cards, the AI evaluation
scripts/                 track_a.py, track_b.py, phase0.py, parks_batch.sh, publish_data.sh, ship.sh, check_secrets.py
src/parkwild/            the Python library: pure batch code, no agents, one DuckDB writer
tests/                   offline tests with fixtures; CI runs them on every push
notebooks/               the narrative walkthroughs of the manual reviews
reports/                 the decision log every filter writes to, and review samples
data/                    gitignored: images, the DuckDB file, model output, exports, batch logs
BUILD_SPEC.md            the build specification the project follows
PROJECT_BRIEF.md         the original brief
DECISIONS.md             architecture decision records and the open-decisions list
EXPERIMENTS.md           the ledger: what was tried, what was measured, what failed
RESULTS.md               the numbers, good or bad
SECURITY.md              threat model and controls
```

## Running it yourself

```bash
make setup                    # .venv with Python 3.12 and the light dependencies
make hooks                    # pre-commit secret scan and pre-push checks
cp .env.example .env          # MAPILLARY_TOKEN, only needed for Track B
make test lint                # offline; no token, no model
cd app && npm ci && npm run dev
```

Bringing a park live, end to end (network, no token):

```bash
scripts/parks_batch.sh arches bryce_canyon      # sightings, export, landmarks, roads, things to do, then a data PR
scripts/publish_data.sh "title" arches          # publish an existing export on its own
node app/scripts/tour-probe.mjs "https://tlappas-23.github.io/parkwild/?park=zion" /tmp/probe 44 8   # watch the tour camera headless
```

Track B needs `make setup-ml` (PyTorch and SpeciesNet, several GB) and runs
on CPU. The runbook is in `docs/USER-GUIDE.md` under "For the owner".

## Data sources and licences

| Source | Used for | Terms |
|---|---|---|
| iNaturalist | research-grade observations, photographs, common names | each record and photograph under the licence its observer chose; shown beside every image |
| GBIF | occurrence datasets with their own review | per dataset; the iNaturalist mirror is skipped by dataset key |
| OpenStreetMap via Overpass | park boundaries, landmarks, roads, trails, amenities | ODbL |
| Wikipedia and Wikimedia Commons | landmark summaries and photographs | CC BY-SA and the licence printed on each photograph; only reusable licences pass |
| Mapillary | street-level imagery for the detection track | CC BY-SA 4.0; image id, contributor and licence stored with every row |
| OpenFreeMap, USGS The National Map, AWS Terrain Tiles | base map, imagery, relief | open; attributed on the map |
| SpeciesNet, MegaDetector, Qwen2.5 via WebLLM, CLIP via Transformers.js | detection, classification, the assistant, the photo helper | Apache 2.0 and MIT; models run locally |

Google Maps and Street View are not used anywhere, by design.

## Security

Reads are public. Everything that can change what is published is locked to
one account: a protected `main` branch, pull requests with required checks,
a secret scan in the pre-commit hook and in CI, no token in the app, a strict
Content Security Policy with no third-party scripts, and hashed data files.
[SECURITY.md](SECURITY.md) has the threat model.

## Status

Eleven parks live: Yellowstone, Grand Teton, Great Smoky Mountains, Grand
Canyon, Zion, Yosemite, Rocky Mountain, Glacier, Acadia, Olympic and
Shenandoah. The other 52 are in a batch that runs unattended and opens a
data pull request after every six parks; the home page shows each park's
status. Open questions and the reasoning behind every choice are in
[DECISIONS.md](DECISIONS.md).
