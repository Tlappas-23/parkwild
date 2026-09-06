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
- **Rotate and tilt** with the four buttons above the zoom control, or a right-drag (two fingers on a phone). The compass resets north.
- **All parks** zooms out to the country; click another park's dot to glide into it.
- The panel folds with the chevron; the "Filters" pill brings it back. It folds on its own when a tour starts.

## Tour

"Take the tour" lands close over each stop in satellite 3D and turns slowly while you read; turn or tilt the map yourself and it waits ten seconds before taking over again. On Next the camera rises over the road and follows the shortest road path to the next stop, climbing higher the longer the leg so the ground passes at a readable pace, then settles close over the stop; the car/plane button on the card switches to a straight flight instead, and the choice is remembered. The card in the corner has three tabs:

- **Wildlife**: the species recorded within 2.5 km, each with a photograph taken near that stop when one exists ("near here").
- **Things to do**: key features, hikes with lengths, camping and lodging with the fees and reservation rules OpenStreetMap carries, and facilities; a plus on each adds it to a route; the same items appear on the map while the tab is open.
- **Photos**: photographs of the place from Wikimedia Commons, and "Look around from here on Mapillary" where street imagery is within 300 m.

Play advances every 14 seconds; the arrows step; the expand button shows more; the minus shrinks the card to a strip; Escape exits. Tapping the map never stops the motion.

## Places

Click any trail, feature, campsite or landmark, in the Things-to-do list or on the map, for its drawer: facts (trail length, elevation, capacity, fee, reservation, difficulty), a Wikipedia summary or an honest "no article", the animals recorded along the whole trail or within a kilometre with near-here photographs, a one-click map filter for the top species, and licensed photographs of the place. The trail is drawn on the map.

## Plan a visit

Choose a start (your location, asked once and never stored, or any landmark), Drive or Hike, and the places you want: all tour stops in one tap, the busiest spots of the species you have filtered, a searched landmark or campsite, or anything added from a card or drawer. "Plan the best route" orders them over the park's real roads and trails, draws the route, and lists each leg with distance, time and a turn-by-turn link. Times assume 35 mph or 5 km/h plus five minutes a stop; routes know nothing of closures, so check nps.gov.

## Species

A grid of every species with a photograph; search by any name; filter mammals or birds. A species page shows the photographs with their observers, sightings, years, the busiest month, and "seen more than usual", the month in which the species' share of sightings most exceeds everyone's, which separates the animal's season from the visitors'. "Show on the map" applies the filter.

## Ask (optional)

Press Enable to download a small language model once (about 1 GB) and run it on your device. Ask in plain words; every sentence cites a numbered fact from this site's data, and "the data doesn't say" is a normal answer. "What did I see?" ranks a photo against the park's species as a suggestion. Nothing you type or photograph leaves your device. "Measure it" runs the fixed question set and prints the table the repository records.

## About

Per park: what the hexagons mean, what the map cannot tell you, sensitive species, exactly where a model is involved and where it is not, road and seasonal bias where measured, sources and licences, and links to these documents.

## For the owner

- **Check the tour camera without eyes on it:** `node app/scripts/tour-probe.mjs "https://tlappas-23.github.io/parkwild/?park=zion" /tmp/probe 44 8` starts headless Chrome, runs the tour, presses Next at 8 s, and leaves camera samples and screenshots in the folder (E-048).

- Add a park: a stanza in `config/parks.toml` (or copy from `config/parks.seed.toml`), then `make track-a PARK=key`, `track_a.py landmarks|roads|amenities --park key`, `make app-data PARK=key`, `track_a.py index`, ship.
- Ship: `scripts/ship.sh "title" body.md` opens a PR with auto-merge; main is protected.
- Review: fill `data/review/species/perspective/review_me.csv`, then `phase0.py species-report --reviewer me`.
