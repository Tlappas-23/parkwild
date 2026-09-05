"""Road and trail length inside a corridor, from OpenStreetMap via Overpass.

PROBLEM: "27,430 images" means nothing until it is images per kilometre of
road. That denominator needs road geometry, and the stack says Overpass.

FIRST ATTEMPT (E-004): POST the query with python-requests' defaults. The main
instance answered HTTP 406 three times; the kumi mirror answered 429. The same
query from curl worked. The difference was the User-Agent: overpass-api.de
refuses the default `python-requests/x.y` string.

CURRENT: a named User-Agent, the lz4 mirror first (same data, fastest in
testing), one query per corridor, generous timeout, back off on 429/504.
Lamar Valley: 179 ways, 58.7 km road, 75.9 km trail.

CONSIDERED, NOT DONE: NPS road centreline shapefiles. Authoritative, but a
second download-and-parse path for a number Overpass gives in one call. May
return for park boundaries in Phase 1.

UNRESOLVED: segment clipping at the bbox edge is crude (geo.path_length_m),
so road km carries maybe ±5%. Fine for a density figure; not for anything
that needs a road network.
"""
from __future__ import annotations

import logging
import time

import requests

from .geo import BBox, path_length_m

log = logging.getLogger(__name__)

# lz4 first: same data as the main instance and answered fastest in testing.
OVERPASS_URLS = (
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
HEADERS = {"User-Agent": "parkwild/0.0.1 (wildlife side project; road length per park corridor)"}

# ROAD_TAGS — BORROWED (OSM wiki, Key:highway; the driveable classes)
# What a Mapillary contributor's car drives on. `track` is deliberately in
# TRAIL_TAGS: in Yellowstone a track is a closed service road, not a drive.
# REVISIT IF: a corridor turns out to have imagery mostly on `track` ways.
ROAD_TAGS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "service", "living_street", "road",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}

# TRAIL_TAGS — BORROWED (OSM wiki, Key:highway; the walked classes)
# Mapillary also has hikers, so trail km is reported alongside road km.
TRAIL_TAGS = {"path", "footway", "track", "bridleway", "cycleway", "steps", "pedestrian"}


def fetch_highways(bbox: BBox, *, timeout_s: int = 120) -> list[dict]:
    """Every highway=* way touching `bbox`, with full geometry.

    Overpass selects ways that intersect the box but returns each way whole,
    so a long highway that clips a corner comes back entire; the length
    summary clips it back."""
    query = f'[out:json][timeout:{timeout_s}];way["highway"]({bbox.as_overpass()});out geom;'
    last_error: Exception | None = None
    for url in OVERPASS_URLS:
        for attempt in range(3):
            try:
                resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=timeout_s + 30)
                # 406 is the default-UA refusal; 429/504 are load. All three mean "try again elsewhere".
                if resp.status_code in (406, 429, 504):
                    log.warning("Overpass %s returned %d; waiting", url, resp.status_code)
                    time.sleep(10 * (attempt + 1))
                    continue
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
                return [
                    {
                        "id": el["id"],
                        "highway": el.get("tags", {}).get("highway"),
                        "name": el.get("tags", {}).get("name"),
                        "coords": [(pt["lon"], pt["lat"]) for pt in el.get("geometry", [])],
                    }
                    for el in elements
                    if el.get("type") == "way"
                ]
            except requests.RequestException as exc:
                last_error = exc
                log.warning("Overpass %s failed (%s); retrying", url, exc)
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Overpass unavailable: {last_error}")


def summarize_length_km(ways: list[dict], bbox: BBox) -> dict[str, float | int]:
    """Kilometres of road / trail / other highway inside the bbox."""
    road = trail = other = 0.0
    for way in ways:
        length = path_length_m(way["coords"], clip_to=bbox) / 1000
        tag = way["highway"]
        if tag in ROAD_TAGS:
            road += length
        elif tag in TRAIL_TAGS:
            trail += length
        else:
            other += length
    return {
        "road_km": round(road, 2),
        "trail_km": round(trail, 2),
        "other_km": round(other, 2),
        "total_km": round(road + trail + other, 2),
        "n_ways": len(ways),
    }
