# Data card: basemap, relief and imagery

| | |
|---|---|
| Vector basemap | OpenFreeMap "liberty" style and fonts: OpenStreetMap roads, water, landcover, labels. No key. ODbL; "© OpenStreetMap contributors" on the map. |
| Relief and 3D | AWS Terrain Tiles (`elevation-tiles-prod`, Terrarium PNG encoding), built by Mapzen from USGS 3DEP, SRTM and others. Open data on S3, no credentials, CORS `*`. Used for the hillshade and MapLibre's terrain at 1.35× exaggeration. |
| Satellite | USGS The National Map, `USGSImageryOnly` tile service. Public domain. No key. |
| Checked | 2026-09-05: each endpoint answered 200 with `Access-Control-Allow-Origin: *` from a plain `curl` |
| Cached | The service worker keeps up to 900 tiles for 30 days, cache-first |

## Known limits

- **Rate limits are undocumented** for the USGS service and the terrain bucket at this volume. If either starts refusing, the map degrades to the vector style (imagery layer empty, no relief), not to an error.
- **Terrain costs GPU.** 3D is off by default for visitors who asked their OS for reduced motion, and a toggle for everyone else.
- **Imagery dates vary** by area; USGS does not expose the capture date per tile.
