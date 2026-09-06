"""Things to do around a place: features, trails, camping, facilities.

PROBLEM: a tour stop names a place and the animals seen there; the owner
wants what a visitor does next: the key features around it, where to hike,
where to camp.

CURRENT: OpenStreetMap again, one Overpass query per park for campsites,
huts and lodges, trailheads, viewpoints, picnic sites, visitor centres and
ranger stations, boat launches, and named natural features (geysers, hot
springs, waterfalls, peaks, caves, arches). Features and facilities are kept
inside the park polygon; camping and lodging anywhere in the bounding box,
because the campground for a stop is often just outside the gate. Named
trails come from the routing graph already baked (roads.json): every trail
edge with a name, summed by name, with a point to draw. The app decides what
is "near" a stop (app/src/tour.ts).

CONSIDERED: the NPS API (campgrounds with reservations and amenities,
official "things to do", public domain) needs a free key; it is the natural
next enrichment and is left as an opt-in. Wikipedia geosearch (too noisy).

UNRESOLVED: OSM's campsite coverage mixes backcountry sites (Yellowstone's
"4R1") with drive-in campgrounds; the `backcountry` and `capacity` tags
separate them when present, which is not always. Fees, reservations and
opening months are copied as tagged, never inferred.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from .config import Park
from .decisionlog import log_filter
from .export import write_park_manifest
from .geo import point_in_geometry
from .overpass import run_query

log = logging.getLogger(__name__)

# AMENITY_KINDS — BORROWED (OSM wiki tags for the things a park visitor does)
# (key, value regex, kind, needs a name, inside the park only)
AMENITY_KINDS: list[tuple[str, str, str, bool, bool]] = [
    ("tourism", "camp_site|caravan_site", "camp", False, False),
    ("tourism", "alpine_hut|wilderness_hut|hotel|motel|hostel|guest_house|chalet", "stay", True, False),
    ("highway", "trailhead", "trailhead", False, True),
    ("tourism", "viewpoint", "viewpoint", False, True),
    ("tourism", "picnic_site", "picnic", False, True),
    ("tourism", "information", "info", True, True),        # narrowed to visitor centres and offices below
    ("amenity", "ranger_station", "info", True, True),
    ("leisure", "slipway|marina", "boat", False, True),
    ("natural", "geyser|hot_spring|spring|waterfall|peak|volcano|cave_entrance|arch", "feature", True, True),
    ("waterway", "waterfall", "feature", True, True),
]
# INFO_TYPES — BORROWED (OSM wiki, Key:information; the two that mean a staffed place)
INFO_TYPES = {"visitor_centre", "office"}

# TRAIL_MIN_M — ARBITRARY (a named trail shorter than this is a spur or a data slip)
TRAIL_MIN_M = 500

# COPIED_TAGS — BORROWED (OSM tags worth carrying to the card, copied verbatim)
COPIED_TAGS = ("capacity", "fee", "reservation", "backcountry", "opening_hours", "website", "ele", "description",
               "drinking_water", "toilets", "operator", "phone", "seasonal")


def _query(park: Park, timeout_s: int) -> str:
    box = park.bbox.as_overpass()
    parts = "".join(f'nwr["{key}"~"^({vals})$"]({box});' for key, vals, _, _, _ in AMENITY_KINDS)
    return f"[out:json][timeout:{timeout_s}];({parts});out tags center;"


def _kind(tags: dict) -> tuple[str, bool, bool] | None:
    for key, vals, kind, needs_name, inside_only in AMENITY_KINDS:
        v = tags.get(key)
        if v and re.fullmatch(vals, v):
            if key == "tourism" and v == "information" and tags.get("information") not in INFO_TYPES:
                return None
            return kind, needs_name, inside_only
    return None


def _default_name(kind: str, tags: dict) -> str:
    sub = tags.get("natural") or tags.get("tourism") or tags.get("highway") or tags.get("leisure") or tags.get("amenity") or kind
    return {"camp_site": "Campsite", "caravan_site": "RV site", "viewpoint": "Viewpoint", "picnic_site": "Picnic site",
            "trailhead": "Trailhead", "slipway": "Boat launch", "marina": "Marina"}.get(sub, sub.replace("_", " ").capitalize())


def items_from_elements(elements: list[dict], boundary: dict | None) -> tuple[list[dict], dict]:
    counts = {"fetched": len(elements), "no_name": 0, "outside": 0, "other_info": 0}
    out: list[dict] = []
    for el in elements:
        tags = el.get("tags", {})
        k = _kind(tags)
        if k is None:
            counts["other_info"] += 1
            continue
        kind, needs_name, inside_only = k
        name = tags.get("name")
        if needs_name and not name:
            counts["no_name"] += 1
            continue
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        if lat is None:
            continue
        if inside_only and boundary is not None and not point_in_geometry(lon, lat, boundary["geometry"]):
            counts["outside"] += 1
            continue
        sub = tags.get("natural") or tags.get("tourism") or tags.get("highway") or tags.get("leisure") or tags.get("amenity") or ""
        out.append({
            "id": f"{el['type']}/{el['id']}", "kind": kind, "sub": sub.replace("_", " "),
            "name": name or _default_name(kind, tags), "named": bool(name),
            "lon": round(lon, 5), "lat": round(lat, 5),
            "tags": {t: tags[t] for t in COPIED_TAGS if t in tags},
        })
    return out, counts


def trails_from_roads(roads: dict) -> list[dict]:
    """Named trail edges summed by name; the point is the midpoint of the
    longest piece, which is where a label sits best."""
    by_name: dict[int, dict] = {}
    for a, b, length, kind, _oneway, name_idx, coords in roads["edges"]:
        if kind != 1 or name_idx < 0:
            continue
        t = by_name.setdefault(name_idx, {"length_m": 0, "pieces": 0, "longest": 0, "point": None})
        t["length_m"] += length
        t["pieces"] += 1
        if length > t["longest"]:
            t["longest"] = length
            t["point"] = coords[len(coords) // 2]
    trails = [{"id": f"trail/{i}", "kind": "trail", "name": roads["names"][i], "length_m": round(t["length_m"]),
               "pieces": t["pieces"], "lon": t["point"][0], "lat": t["point"][1]}
              for i, t in by_name.items() if t["length_m"] >= TRAIL_MIN_M and t["point"]]
    trails.sort(key=lambda t: -t["length_m"])
    return trails


def build_amenities(park: Park, out_dir: Path, *, timeout_s: int = 120) -> dict:
    boundary_path = out_dir / "boundary.geojson"
    boundary = json.loads(boundary_path.read_text()) if boundary_path.exists() else None
    elements = run_query(_query(park, timeout_s), timeout_s=timeout_s)
    items, counts = items_from_elements(elements, boundary)
    log_filter("amenities.osm", "OSM campsites, lodging, trailheads, viewpoints, picnic sites, visitor centres, boat launches, "
               "named natural features; facilities inside the boundary, camping anywhere in the bbox",
               counts["fetched"], len(items), park=park.key, **{k: v for k, v in counts.items() if k != "fetched"})
    roads_path = out_dir / "roads.json"
    trails = trails_from_roads(json.loads(roads_path.read_text())) if roads_path.exists() else []
    if not roads_path.exists():
        log.warning("%s: no roads.json yet (run roads first); no trails", park.key)
    payload = {"park": park.key, "fetched": datetime.now(UTC).isoformat(timespec="seconds"),
               "attribution": "© OpenStreetMap contributors, ODbL",
               "kinds": ["feature", "trailhead", "viewpoint", "picnic", "info", "boat", "camp", "stay", "trail"],
               "items": items, "trails": trails}
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "amenities.json"
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    write_park_manifest(out_dir, park.key)
    by_kind: dict[str, int] = {}
    for it in items:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    return {"items": len(items), "by_kind": by_kind, "trails": len(trails), "trail_km": round(sum(t["length_m"] for t in trails) / 1000),
            "bytes": path.stat().st_size, **{k: v for k, v in counts.items() if k != "fetched"}}
