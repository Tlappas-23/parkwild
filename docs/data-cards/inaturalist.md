# Data card: iNaturalist observations

| | |
|---|---|
| What | Community observations with photos, identified to research grade by at least two agreeing identifiers |
| Access | API v1, no key, ~1 request/s, 10,000/day; `id_above` paging |
| Filter used | `place_id` of the park (exact boundary), `quality_grade=research`, `iconic_taxa=Mammalia,Aves`, all dates |
| License | Per observation, chosen by the observer: CC0, CC BY, CC BY-NC, CC BY-SA and others, or all rights reserved. Stored per record. |
| Stored per record | observation id, observer login, taxon (id, name, common name, rank, class), observed time and date, public coordinates, positional accuracy, coordinate status, license, URL, raw JSON |
| Yellowstone (place 10211) | 51,642 research-grade Mammalia + Aves observations reported by the API on 2026-09-05 |

## Obscured coordinates

iNaturalist fuzzes the public location of threatened taxa (`taxon_geoprivacy`) and of anything the observer hides (`geoprivacy`). The public point is the centre of a ~0.2° cell with `public_positional_accuracy` around 28 km. These rows are stored with `coordinate_status='obscured'`, count in totals and seasonality, and never enter a map cell. Nothing in this project attempts to recover the true position. Species with any taxon-obscured observation are also coarsened automatically in the export (config/suppression.toml, rule 2).

## Known biases

- **Effort follows people.** Roadside pull-outs, boardwalks and visitor centres are heavily observed; the backcountry is not.
- **Summer.** June to August dominate.
- **Charisma.** Bison, elk and bears are photographed far more than shrews. Counts are observations, not abundance.
- **Identification quality.** Research grade means two agreeing identifiers, not an expert; common confusions (elk vs mule deer at distance) exist at a low rate.

## Use in this project

The Track A backbone: every row is `confidence_basis='human_verified'`. Also the ground truth for validating detections distributionally (Phase 3).
