# Data card: landmarks, tour stops and the park outline

| | |
|---|---|
| What | Named places for the virtual tour, and the park boundary the map is cut to |
| Landmarks | OpenStreetMap features inside the park carrying a `wikidata` tag, in the kinds listed in `parkwild.landmarks.KINDS`, fetched through Overpass (named User-Agent) |
| Tour stops | An ordered, hand-picked list per park in config/parks.toml, matched to landmarks by name; a configured coordinate where OSM has no feature (valleys) |
| Descriptions | The opening paragraph of each stop's English Wikipedia article, from the REST summary endpoint, fetched once at 1 request/s |
| Boundary | The iNaturalist place polygon for the park's `inat_place_id`, the same boundary the sightings were filtered by, rounded to 4 decimals |
| Licences | OSM: ODbL, "© OpenStreetMap contributors" on the map; the extract is published in this public repo. Wikipedia text: CC BY-SA 4.0, linked beside every excerpt. iNaturalist place geometry: shown as an outline, credited on the About page. |
| Stored | data/export/<park>/landmarks.json and boundary.geojson, hashed into manifest.json |

## Known limits

- **Notability is a Wikidata tag.** A landmark without a Wikidata item does not exist here; a geyser with one does. Per-kind caps (20) keep Yellowstone from being a map of geysers.
- **Matching is by name.** "Old Faithful" is a geyser node in OSM; "Norris Geyser Basin" is not a feature at all. `missing_stops` in the output lists what did not match; fix the config, do not guess.
- **Excerpts are not curated.** The Lamar Valley article is about the river. A per-stop `@wiki` title in config points at a better article where one exists.
