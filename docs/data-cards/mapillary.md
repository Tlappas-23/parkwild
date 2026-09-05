# Data card: Mapillary street-level imagery

| | |
|---|---|
| What | Crowdsourced street-level photos with GPS, compass heading, timestamp and camera type |
| Access | Graph API v4, free client token, `Authorization: OAuth` header |
| License | CC BY-SA 4.0 (terms §3b); Mapillary logo and link back required on published output (§11) |
| Stored per image | image ID, contributor username and ID, license, page URL, raw and SfM positions, heading, camera type, dimensions, sequence, thumbnail URLs, raw JSON |
| Coverage measured 2026-09-05 | Lamar Valley 27,430 images / 55 sequences / 8 contributors; Moose-Wilson 24,231 / 88; Cades Cove 39,410 / 123 |
| Date range | Lamar 2014-09 to 2024-08; Cades Cove to 2026-06 |
| Density | Lamar: 467 images per road km (59 km of OSM road in the bbox) |

## Known biases

- **One contributor dominates.** 87% of Lamar's images are 4096 x 2048 spherical panoramas from a single account in June to August 2024. Perspective frames (13%) are 2014 to 2018 from five accounts. Any "trend over time" is a trend in who uploaded.
- **Roads only.** Cameras are on the road; animals more than ~200 m from it are small or absent. Measured as road bias in Phase 3.
- **Summer.** Uploads cluster June to August; see seasonal bias.
- **Resolution.** Panoramas give ~11 px per degree; a bison at 100 m is ~11 px tall. Perspective originals average 3789 x 2843.
- **Orientation tags.** 13 of 400 sampled frames carry a 180° EXIF rotation; SpeciesNet and the review renderer both apply it.

## API behaviour not in the docs (measured)

- The 2000-row cap is fuzzy: tiles returning 1879 to 1973 rows were truncated. The crawler splits at 1500.
- Tiles with too many images return HTTP 500 at any `limit`; quarters answer normally.

## Use in this project

Index only, plus a sampled download for detection. Images are never redistributed; the app links to the Mapillary page. Derived coordinates are published with image ID, contributor and license.
