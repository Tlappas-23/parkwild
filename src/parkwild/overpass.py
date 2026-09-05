"""
Overpass API client, just enough to measure how much road and trail sits inside
a corridor bbox. That number turns "we have 3,800 images" into "images per km",
which is the density figure Phase 0 asks for.

Overpass is free and shared, so: one query per corridor, a generous timeout,
and fall back to a mirror if the main instance is busy.

Learned 2026-09-05: overpass-api.de answers HTTP 406 to python-requests'
default User-Agent, while the same query from curl or with a named UA returns
normally. So every request identifies this project by name.
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

# OSM highway=* values that a car (or at least a Mapillary contributor's car)
# drives on, versus ones that are walked. Street-level imagery is mostly the
# first group, but Mapillary also has hikers, so I report both.
ROAD_TAGS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "service", "living_street", "road",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}
TRAIL_TAGS = {"path", "footway", "track", "bridleway", "cycleway", "steps", "pedestrian"}


def fetch_highways(bbox: BBox, *, timeout_s: int = 120) -> list[dict]:
    """Return every highway=* way touching `bbox`, with its full geometry.

    Overpass selects ways that intersect the box but returns their entire
    geometry, so a long highway that clips one corner comes back whole. The
    length summary clips it back (see geo.path_length_m)."""
    query = f'[out:json][timeout:{timeout_s}];way["highway"]({bbox.as_overpass()});out geom;'
    last_error: Exception | None = None
    for url in OVERPASS_URLS:
        for attempt in range(3):
            try:
                resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=timeout_s + 30)
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
