# Data card: roads and trails (routing graph)

| | |
|---|---|
| What | OpenStreetMap `highway=*` ways in the park's bounding box, as a node/edge graph the app routes over |
| Kept | Inside the park polygon: every driveable and walkable class except service roads, living streets and `highway=road`; outside it: motorway to tertiary only (the approach roads, not the gateway towns' streets); `access=private|no|military` dropped everywhere |
| Edges | Cut at junctions, way ends and every 300 m; geometry simplified at 5 m; length in metres, kind (road/trail), one-way flag, name |
| Licence | ODbL; "© OpenStreetMap contributors" in the file and on the map |
| Stored | data/export/<park>/roads.json, hashed into manifest.json; loaded by the app only when a route is asked for |
| Sizes | Yellowstone 1.48 MB (403 KB gzipped), Grand Teton 613 KB, Great Smoky 2.0 MB |

## Known limits

- **No closures, no seasons, no grades.** Many park roads close from November to April; the planner says so and links nps.gov.
- **Turn restrictions are ignored;** one-way streets are honoured.
- **Snapping.** A site is routed to the nearest graph node; a road vertex is never more than 150 m from the road itself, but a lake's point is its centre, so when the nearest road is over 1 km from the point the leg says so.
- **Speeds are assumptions**, not measurements: 35 mph driving, 5 km/h walking, five minutes per stop.
