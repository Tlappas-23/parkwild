"""iNaturalist API v1 client and normaliser for the `sightings` schema.

PROBLEM: the reference dataset the app can ship on regardless of detection.
Yellowstone has 51,642 research-grade mammal and bird observations; page
size is 200 and page*per_page is capped at 10,000, so page numbers cannot
reach them.

CURRENT: `id_above` paging in ascending id order (no cap), one request per
second, `place_id` for the exact park boundary. Obscured coordinates are
kept and flagged, never recovered: iNaturalist fuzzes the location of
threatened taxa and of anything the observer hid, and says so in the record
(`obscured`, `geoprivacy`, `taxon_geoprivacy`); the public point is the
centre of a ~0.2 degree cell, not the animal. Those rows count in totals and
seasonality and never enter a map cell.

CONSIDERED, NOT DONE: the v2 API with field selection (smaller responses).
v1 returns the whole record, which is stored as raw JSON and turned out to
be useful (taxon_geoprivacy feeds the suppression list).

UNRESOLVED: the ingest is slow (about 1,300 records a minute) because the
API answers in 3 to 8 s per page; it is a one-time cost per park and is not
optimised.
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

API = "https://api.inaturalist.org/v1"
HEADERS = {"User-Agent": "parkwild/0.0.1 (wildlife side project; park sightings for a public map)"}
# ICONIC_TAXA — BORROWED (build spec, Phase 1: "Mammalia and Aves")
ICONIC_TAXA = ("Mammalia", "Aves")

# PER_PAGE — BORROWED (iNaturalist API docs: maximum 200)
PER_PAGE = 200

# MIN_INTERVAL_S — BORROWED (iNaturalist API recommendations: at most ~1 request/s,
# 10,000/day). One park is ~260 pages, well inside the daily budget.
MIN_INTERVAL_S = 1.0

LICENSE_NAMES = {
    "cc0": "CC0 1.0", "cc-by": "CC BY 4.0", "cc-by-nc": "CC BY-NC 4.0", "cc-by-sa": "CC BY-SA 4.0",
    "cc-by-nd": "CC BY-ND 4.0", "cc-by-nc-sa": "CC BY-NC-SA 4.0", "cc-by-nc-nd": "CC BY-NC-ND 4.0",
}


class INatError(RuntimeError):
    pass


def _get(path: str, params: dict, *, session: requests.Session | None = None, retries: int = 5) -> dict:
    session = session or requests
    for attempt in range(retries + 1):
        try:
            resp = session.get(f"{API}{path}", params=params, headers=HEADERS, timeout=90)
        except requests.RequestException as exc:
            log.warning("iNat request error (%s); retrying", exc)
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = min(120, 5 * 2 ** attempt)
            log.warning("iNat HTTP %d; waiting %ds", resp.status_code, wait)
            time.sleep(wait)
            continue
        raise INatError(f"HTTP {resp.status_code} for {path} {params}: {resp.text[:300]}")
    raise INatError(f"gave up on {path} after {retries} retries")


def find_places(query: str) -> list[dict]:
    """Place lookup, e.g. 'Yellowstone National Park'. Returns id, name, type,
    and bbox for each match so the right one can be picked by hand."""
    data = _get("/places/autocomplete", {"q": query, "per_page": 10})
    out = []
    for p in data.get("results", []):
        bb = p.get("bounding_box_geojson") or {}
        coords = bb.get("coordinates", [[]])[0] if bb else []
        lons = [c[0] for c in coords] or [None]
        lats = [c[1] for c in coords] or [None]
        out.append({
            "id": p["id"], "name": p.get("display_name") or p.get("name"), "place_type": p.get("place_type"),
            "admin_level": p.get("admin_level"),
            "bbox": [min(lons), min(lats), max(lons), max(lats)] if coords else None,
        })
    return out


def iter_observations(
    *,
    place_id: int | None = None,
    bbox: BBox | None = None,
    iconic_taxa: tuple[str, ...] = ICONIC_TAXA,
    quality_grade: str = "research",
    d1: str | None = None,
    d2: str | None = None,
    per_page: int = PER_PAGE,
    max_records: int | None = None,
    session: requests.Session | None = None,
) -> Iterator[dict]:
    """Yield raw observation records, ascending by id, using id_above paging."""
    if place_id is None and bbox is None:
        raise ValueError("need place_id or bbox")
    params: dict = {
        "quality_grade": quality_grade,
        "iconic_taxa": list(iconic_taxa),
        "per_page": per_page,
        "order": "asc",
        "order_by": "id",
        "geo": "true",
        "verifiable": "true",
    }
    if place_id is not None:
        params["place_id"] = place_id
    if bbox is not None:
        params.update({"swlng": bbox.min_lon, "swlat": bbox.min_lat, "nelng": bbox.max_lon, "nelat": bbox.max_lat})
    if d1:
        params["d1"] = d1
    if d2:
        params["d2"] = d2
    session = session or requests.Session()
    id_above = 0
    n = 0
    while True:
        time.sleep(MIN_INTERVAL_S)
        data = _get("/observations", {**params, "id_above": id_above}, session=session)
        results = data.get("results", [])
        if not results:
            return
        for obs in results:
            yield obs
            n += 1
            if max_records and n >= max_records:
                return
        id_above = results[-1]["id"]
        log.info("iNat: %d fetched (total_results=%s)", n, data.get("total_results"))
        if len(results) < per_page:
            return


def _parse_time(obs: dict) -> tuple[datetime | None, str | None]:
    """(observed_at UTC naive, observed_on ISO date). time_observed_at is ISO
    with offset when the observer gave a time; observed_on is always a date."""
    observed_on = obs.get("observed_on")
    ts = obs.get("time_observed_at")
    observed_at = None
    if ts:
        try:
            observed_at = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)
        except ValueError:
            observed_at = None
    return observed_at, observed_on


def normalize(obs: dict, park: str) -> dict:
    """One raw observation -> one `sightings` row."""
    taxon = obs.get("taxon") or {}
    user = obs.get("user") or {}
    geojson = obs.get("geojson") or {}
    coords = geojson.get("coordinates") if geojson.get("type") == "Point" else None
    lon, lat = (float(coords[0]), float(coords[1])) if coords else (None, None)
    obscured = bool(obs.get("obscured")) or obs.get("geoprivacy") in ("obscured", "private") or obs.get("taxon_geoprivacy") in ("obscured", "private")
    if lon is None:
        status = "private" if obs.get("geoprivacy") == "private" else "missing"
    elif obscured:
        status = "obscured"
    else:
        status = "open"
    observed_at, observed_on = _parse_time(obs)
    license_code = obs.get("license_code")
    license_name = LICENSE_NAMES.get(license_code or "", license_code or "all rights reserved")
    url = obs.get("uri") or f"https://www.inaturalist.org/observations/{obs['id']}"
    observer = user.get("login")
    return {
        "sighting_id": f"inaturalist:{obs['id']}",
        "source": "inaturalist",
        "source_id": str(obs["id"]),
        "dataset": "inaturalist",
        "park": park,
        "confidence_basis": "human_verified",
        "taxon_id": str(taxon.get("id")) if taxon.get("id") is not None else None,
        "scientific_name": taxon.get("name"),
        "common_name": taxon.get("preferred_common_name"),
        "taxon_rank": taxon.get("rank"),
        "taxon_class": taxon.get("iconic_taxon_name"),
        "observed_at": observed_at,
        "observed_on": observed_on,
        "lon": lon,
        "lat": lat,
        # public_positional_accuracy already reflects obscuring; positional_accuracy is the GPS figure.
        "positional_accuracy_m": obs.get("public_positional_accuracy") or obs.get("positional_accuracy"),
        "coordinate_status": status,
        "observer": observer,
        "license": license_name,
        "url": url,
        "attribution": f"{observer or 'iNaturalist user'} via iNaturalist, {license_name}, {url}",
        "duplicate_of": None,
        "raw_json": json.dumps(obs, separators=(",", ":")),
    }
