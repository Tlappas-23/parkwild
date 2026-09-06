# parkwild: how to use the site

https://tlappas-23.github.io/parkwild/ · works in any modern browser; the 3D terrain and the Ask page need WebGPU (Chrome, Edge, Safari 18).

## Parks (home)

Cards for every open park with a photograph, species and sighting counts, and the tour length. Type in "Find a park" to filter. Below the cards, the country map shows all 63 parks: filled dots open, hollow dots being gathered, faint dots not started. Click a filled dot or a card to enter a park.

## Map

You arrive on the whole park outline. Blue hexagons are places where people recorded animals; deeper blue means more sightings. Amber appears only where the roadside camera pass added a sighting of its own (Yellowstone).

- **Terrain / Satellite / 3D** at the top of the left panel. Satellite drapes USGS imagery over the relief.
- **Species** search: type "elk", "bison", a scientific name or an old name; the map keeps only cells with that species and the counts switch to that species.
- **Years** two sliders bound the span.
- **Tap a hexagon** for its drawer: sightings and years, the photographs taken in that cell (credited), and a link that opens the same box on iNaturalist so you can check it yourself. With a species filter on, the drawer leads with that species and folds the rest away. "Add this spot to a route" sends it to the planner.
- **Weather** at the top of the left panel: conditions now and the next three days at the park's busiest place, and what this month is usually like there (ten-year normals). Fetched by your browser from Open-Meteo when you look; nothing is stored.
- **Rotate and tilt** with the four buttons above the zoom control, or a right-drag (two fingers on a phone). The compass resets north.
- **All parks** zooms out to the country; click another park's dot to glide into it.
- The panel folds with the chevron; the "Filters" pill brings it back. It folds on its own when a tour starts.

## Tour

"Take the tour" lands close over each stop in satellite 3D and turns slowly while you read; drag, turn, tilt or zoom the map yourself and it waits five seconds before taking over again (a tap does not interrupt it). On Next the camera rises over the road and follows the shortest road path to the next stop, climbing higher the longer the leg so the ground passes at a readable pace, then settles close over the stop; the car/plane button on the card switches to a straight flight instead, and the choice is remembered. The card in the corner has three tabs:

- **Wildlife**: the species recorded within 2.5 km, each with a photograph taken near that stop when one exists ("near here").
- **Things to do**: key features, hikes with lengths, camping and lodging with the fees and reservation rules OpenStreetMap carries, and facilities; a plus on each adds it to a route; the same items appear on the map while the tab is open.
- **Photos**: photographs of the place from Wikimedia Commons, and "Look around from here on Mapillary" where street imagery is within 300 m.

The tour plays by itself: each stop holds for about 14 seconds, the thin bar along the top of the card counts it down, then the camera moves on. Pause holds the stop; Play moves on within a second when the stop has already had its time. The arrows step; the expand button shows more; the minus shrinks the card to a strip; Escape exits. Tapping the map to open a cell never stops the tour.

## Places

Click any trail, feature, campsite or landmark, in the Things-to-do list or on the map, for its drawer: facts (trail length, elevation, capacity, fee, reservation, difficulty), a Wikipedia summary or an honest "no article", the animals recorded along the whole trail or within a kilometre with near-here photographs, a one-click map filter for the top species, and licensed photographs of the place. The trail is drawn on the map.

## Plan a visit

Choose a start (your location, asked once and never stored, or any landmark), Drive or Hike, and the places you want: all tour stops in one tap, the busiest spots of the species you have filtered, a searched landmark or campsite, or anything added from a card or drawer. "Plan the best route" orders them over the park's real roads and trails, draws the route, and lists each leg with distance, time and a turn-by-turn link. Times assume 35 mph or 5 km/h plus five minutes a stop; routes know nothing of closures, so check nps.gov.

## Places

Every named trail, site, viewpoint, campground and facility in the park, ordered by how many sightings people recorded within reach of it (500 m of a point, 300 m of a trail). That is where observers went, the only free measure of where visitors go; it is not a visitor count. Filter by kind, search, or sort by longest trail, by Wikipedia readers a month (landmarks with an article), or A to Z. Each row shows a twelve-month sparkline and its busiest months. Open a place for its photograph and Wikipedia summary, the weather there now and this month's typical weather, the month-by-month chart, the animals people recorded there with a photograph each, and buttons to show it on the map or add it to a route. The file loads when you first open the page.

## Species

Two scopes at the top: **In this park** is the photo grid of everything recorded in the open park; **All parks** searches every park at once and each row says where the animal turns up and how often. Type "elk", "bison", a scientific name or an old name. Open a species for photographs, months, sources, and **Where people see them, park by park**: every park with its count and busiest cell, and a "Show in" button that opens that park's map filtered to the species, landing on that cell with its drawer open. A sensitive species that is not mapped shows counts only; a coarsened one says so. The "Show in" button under the photograph does the same for the open park.

## Ask (optional)

Press Enable to download a small language model once (about 1 GB) and run it on your device. Ask in plain words; every sentence cites a numbered fact from this site's data, and "the data doesn't say" is a normal answer. "What did I see?" ranks a photo against the park's species as a suggestion. Nothing you type or photograph leaves your device. "Measure it" runs the fixed question set and prints the table the repository records.

## About

Per park: what the hexagons mean, what the map cannot tell you, sensitive species, exactly where a model is involved and where it is not, road and seasonal bias where measured, sources and licences, and links to these documents.

## Maintaining the site

- **Keep the data fresh:** `scripts/refresh.sh` runs from cron on the 1st and 15th at 03:00: for every live park it pulls only the sightings that changed since the last run, re-exports, rebuilds the places, refreshes the climate normals when they are older than a season, and opens one data PR. It refuses to start while the park batch holds the database. `SINCE=2026-08-01 scripts/refresh.sh` forces a window.
- **Bring parks live unattended:** `nohup scripts/parks_batch.sh arches bryce_canyon ... > data/batch/batch.log 2>&1 &` runs sightings, export, landmarks, roads and things to do per park and opens a data PR after every six (`GROUP=` to change). `scripts/publish_data.sh "title" park ...` publishes exports on their own. Neither touches the working tree: the PR is built in a fresh worktree.
- **Check the tour camera without eyes on it:** `node app/scripts/tour-probe.mjs "https://tlappas-23.github.io/parkwild/?park=zion" /tmp/probe 44 8` starts headless Chrome, runs the tour, presses Next at 8 s, and leaves camera samples and screenshots in the folder (E-048).

- Add a park: a stanza in `config/parks.toml` (or copy from `config/parks.seed.toml`), then `make track-a PARK=key`, `track_a.py landmarks|roads|amenities --park key`, `make app-data PARK=key`, `track_a.py index`, ship.
- Ship: `scripts/ship.sh "title" body.md` opens a PR with auto-merge; main is protected.
- Review: fill `data/review/species/perspective/review_me.csv`, then `phase0.py species-report --reviewer me`.
