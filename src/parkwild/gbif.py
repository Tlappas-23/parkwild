"""
GBIF occurrence API client and normaliser for the `sightings` schema.

No key is needed for search. GBIF aggregates hundreds of datasets, including a
full mirror of iNaturalist's research-grade observations, so:

- the iNaturalist dataset is skipped outright here (exact duplicates of what
  the iNaturalist ingest already stored), and the count is logged;
- records without coordinates are skipped;
- coordinate precision is judged from `coordinateUncertaintyInMeters` and the
  `dataGeneralizations` / `informationWithheld` flags. Anything coarser than
  1 km is stored as 'obscured' and kept out of the cell map.

The search endpoint pages by offset up to 100,000 results per query, so big
queries are split by year automatically.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import requests

from .geo import BBox

log = logging.getLogger(__name__)

API = "https://api.gbif.org/v1"
HEADERS = {"User-Agent": "parkwild/0.0.1 (wildlife side project; park sightings for a public map)"}
INAT_DATASET_KEY = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"    # iNaturalist research-grade observations
EBIRD_DATASET_KEY = "4fa7b334-ce0d-4e88-aaae-2e0c138d049e"   # eBird Observation Dataset
CLASS_KEYS = {"Mammalia": 359, "Aves": 212}
BASIS_OF_RECORD = ("HUMAN_OBSERVATION", "MACHINE_OBSERVATION")
PAGE = 300                 # documented maximum
OFFSET_CAP = 100_000       # documented maximum offset for search
OBSCURED_UNCERTAINTY_M = 1000.0
MIN_INTERVAL_S = 0.3


class GBIFError(RuntimeError):
    pass


def _get(path: str, params: dict, *, session: requests.Session | None = None, retries: int = 5) -> dict:
    session = session or requests
    for attempt in range(retries + 1):
        try:
            resp = session.get(f"{API}{path}", params=params, headers=HEADERS, timeout=120)
        except requests.RequestException as exc:
            log.warning("GBIF request error (%s); retrying", exc)
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = min(120, 5 * 2 ** attempt)
            log.warning("GBIF HTTP %d; waiting %ds", resp.status_code, wait)
            time.sleep(wait)
            continue
        raise GBIFError(f"HTTP {resp.status_code} for {path} {params}: {resp.text[:300]}")
    raise GBIFError(f"gave up on {path} after {retries} retries")


def _base_params(bbox: BBox, class_key: int, **extra) -> dict:
    return {
        "decimalLatitude": f"{bbox.min_lat},{bbox.max_lat}",
        "decimalLongitude": f"{bbox.min_lon},{bbox.max_lon}",
        "classKey": class_key,
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "basisOfRecord": list(BASIS_OF_RECORD),
        **extra,
    }


def count(bbox: BBox, class_key: int, **extra) -> int:
    return int(_get("/occurrence/search", {**_base_params(bbox, class_key, **extra), "limit": 0})["count"])


def count_by_dataset(bbox: BBox, class_key: int, **extra) -> list[tuple[str, int]]:
    """Facet on datasetKey so the iNaturalist / eBird share is visible before
    ingesting anything."""
    data = _get("/occurrence/search", {**_base_params(bbox, class_key, **extra), "limit": 0, "facet": "datasetKey", "facetLimit": 20})
    facets = data.get("facets", [])
    if not facets:
        return []
    return [(c["name"], int(c["count"])) for c in facets[0].get("counts", [])]


def iter_occurrences(
    bbox: BBox,
    class_key: int,
    *,
    year: str | None = None,
    max_records: int | None = None,
    session: requests.Session | None = None,
    _depth: int = 0,
) -> Iterator[dict]:
    """Yield raw occurrences. If a query would exceed the offset cap it is split
    by year (then by half-ranges of years) until each piece fits."""
    session = session or requests.Session()
    extra = {"year": year} if year else {}
    total = count(bbox, class_key, **extra)
    if total > OFFSET_CAP:
        lo, hi = _year_bounds(year)
        if hi - lo < 1:
            log.error("GBIF: %d records in %s exceed the offset cap and cannot be split further; truncating", total, year)
        else:
            mid = (lo + hi) // 2
            for sub in (f"{lo},{mid}", f"{mid + 1},{hi}"):
                yield from iter_occurrences(bbox, class_key, year=sub, max_records=max_records, session=session, _depth=_depth + 1)
            return
    offset = 0
    n = 0
    while offset < min(total, OFFSET_CAP):
        time.sleep(MIN_INTERVAL_S)
        data = _get("/occurrence/search", {**_base_params(bbox, class_key, **extra), "limit": PAGE, "offset": offset}, session=session)
        results = data.get("results", [])
        if not results:
            return
        for occ in results:
            yield occ
            n += 1
            if max_records and n >= max_records:
                return
        offset += len(results)
        if data.get("endOfRecords"):
            return
        if offset % 3000 == 0:
            log.info("GBIF: %d / %d fetched (%s)", offset, total, year or "all years")


def _year_bounds(year: str | None) -> tuple[int, int]:
    if not year:
        return 1800, datetime.now().year
    if "," in year:
        lo, hi = year.split(",")
        return int(lo), int(hi)
    return int(year), int(year)


def _parse_event(occ: dict) -> tuple[datetime | None, str | None]:
    """eventDate may be an ISO instant, a date, or a range 'a/b'. Fall back to
    year/month/day fields for the date."""
    ev = occ.get("eventDate")
    observed_at = None
    observed_on = None
    if ev:
        first = ev.split("/")[0]
        try:
            if "T" in first:
                dt = datetime.fromisoformat(first.replace("Z", "+00:00"))
                observed_at = (dt.astimezone(UTC) if dt.tzinfo else dt).replace(tzinfo=None)
                observed_on = observed_at.date().isoformat()
            else:
                observed_on = first[:10] if len(first) >= 10 else None
        except ValueError:
            pass
    if observed_on is None and occ.get("year") and occ.get("month") and occ.get("day"):
        observed_on = f"{occ['year']:04d}-{occ['month']:02d}-{occ['day']:02d}"
    return observed_at, observed_on


def normalize(occ: dict, park: str) -> dict:
    lon, lat = occ.get("decimalLongitude"), occ.get("decimalLatitude")
    unc = occ.get("coordinateUncertaintyInMeters")
    generalized = bool(occ.get("dataGeneralizations")) or bool(occ.get("informationWithheld"))
    if lon is None or lat is None:
        status = "missing"
    elif generalized or (unc is not None and unc > OBSCURED_UNCERTAINTY_M):
        status = "obscured"
    else:
        status = "open"
    observed_at, observed_on = _parse_event(occ)
    url = occ.get("references") or f"https://www.gbif.org/occurrence/{occ['key']}"
    observer = occ.get("recordedBy")
    license_ = occ.get("license")
    dataset = occ.get("datasetKey")
    dataset_title = occ.get("datasetName") or dataset
    return {
        "sighting_id": f"gbif:{occ['key']}",
        "source": "gbif",
        "source_id": str(occ["key"]),
        "dataset": dataset,
        "park": park,
        "confidence_basis": "human_verified",
        "taxon_id": str(occ.get("taxonKey")) if occ.get("taxonKey") is not None else None,
        "scientific_name": occ.get("species") or occ.get("acceptedScientificName") or occ.get("scientificName"),
        "common_name": occ.get("vernacularName"),
        "taxon_rank": (occ.get("taxonRank") or "").lower() or None,
        "taxon_class": occ.get("class"),
        "observed_at": observed_at,
        "observed_on": observed_on,
        "lon": float(lon) if lon is not None else None,
        "lat": float(lat) if lat is not None else None,
        "positional_accuracy_m": unc,
        "coordinate_status": status,
        "observer": observer,
        "license": license_,
        "url": url,
        "attribution": f"{observer or 'unknown observer'} via GBIF ({dataset_title}), {license_ or 'license unspecified'}, {url}",
        "duplicate_of": None,
        "raw_json": json.dumps(occ, separators=(",", ":")),
    }
