# Data card: GBIF-mediated occurrences

| | |
|---|---|
| What | Occurrence records aggregated from hundreds of publishers, each with its own dataset, license and precision |
| Access | Occurrence search API, no key, `limit<=300`, `offset<=100,000` (queries are split by year past that) |
| Filter used | park bbox (GBIF has no place filter), `classKey` Mammalia (359) / Aves (212), `hasCoordinate`, no geospatial issues, `basisOfRecord` HUMAN_OBSERVATION or MACHINE_OBSERVATION |
| License | Per record (CC0, CC BY, CC BY-NC per dataset). Dataset key and title stored per record. |
| Stored per record | GBIF key, dataset key, taxon key/name/rank/class, vernacular name, event time and date, coordinates, uncertainty, coordinate status, recordedBy, license, URL, raw JSON |

## What is in it for Yellowstone (measured 2026-09-05)

| Class | Total | iNaturalist mirror | eBird | Other datasets |
|---|---|---|---|---|
| Mammalia | 26,248 | 25,292 | 0 | 956 |
| Aves | 445,426 | 16,280 | 421,940 | 7,206 |

- The iNaturalist mirror is **skipped by dataset key** (exact duplicates of the direct ingest).
- eBird is **not ingested** (decision O-4): checklist locations are hotspot centroids, and it would be nine tenths of the data at the worst accuracy in it.

## Precision handling

`coordinateUncertaintyInMeters` over 1 km, or any `dataGeneralizations` / `informationWithheld` flag, marks the record `obscured`: counted, never mapped.

## Known biases

- **Dataset mix.** "Other datasets" are a grab-bag: research projects, museum observation programmes, apps. Effort and precision vary per dataset; the dataset key is on every row so they can be split later.
- **Date formats.** Ranges are truncated to their first day.
- **Bbox, not boundary.** The park's bounding rectangle includes land outside the park; records there are labelled with the park key anyway. Exact boundary filtering is a Phase 1 follow-up using the NPS boundary.

## Use in this project

Second source for Track A, `confidence_basis='human_verified'`, deduplicated against iNaturalist on species, date, distance and observer/time.
