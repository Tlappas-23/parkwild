"""Park roads and trails as a small graph, so the app can give directions
inside the park without a routing service.

PROBLEM: I want to stand somewhere, pick sites, and get the best route ("click which sites and
get the best route". Every hosted router is either paid, keyed (a key in a
static site is public), or a demo server that asks not to be used in
production. The brief is zero cost and no backend.

FIRST ATTEMPT: straight lines between sites with a road-factor multiplier.
Useless in Yellowstone, where the Grand Loop makes two points 5 km apart by
air 60 km apart by road.

CURRENT: OpenStreetMap highways inside the park's bounding box (which takes
in the gateway towns), fetched once through Overpass, cut into edges at
junctions and every MAX_EDGE_M, geometry simplified, written as one JSON
file the browser loads only when someone asks for a route. Dijkstra and the
visiting order run in the browser (app/src/routing.ts). Roads and trails
are kept apart so "drive" and "hike" can differ.

CONSIDERED: OSRM's public demo (explicitly not for production); GraphHopper
and OpenRouteService (free tiers need a key); Valhalla self-hosted (a
backend). NPS's own road GIS (no trails, one more licence to track).

UNRESOLVED: no closures, no seasons, no elevation. Park roads close for
months; the app says so beside every route and links the NPS page. Access
tags are trusted as OSM has them.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from .config import Park
from .decisionlog import log_filter
from .export import write_park_manifest
from .geo import haversine_m, point_in_geometry
from .overpass import ROAD_TAGS, TRAIL_TAGS, run_query

log = logging.getLogger(__name__)

# MAX_EDGE_M — ASSUMED (a site snaps to the nearest graph node; 300 m caps
# that error at 150 m, about the H3 cell size, and more nodes buy nothing)
# REVISIT IF: routes visibly start or end short of a site.
MAX_EDGE_M = 300.0

# SIMPLIFY_M — ARBITRARY (Douglas-Peucker tolerance; 5 m keeps every bend a
# map at zoom 14 can show and roughly halves the file)
SIMPLIFY_M = 5.0

# COORD_DECIMALS — ARBITRARY (five decimals is about a metre)
COORD_DECIMALS = 5

# NO_ACCESS — BORROWED (OSM wiki, Key:access; the values that mean "not for the public")
NO_ACCESS = {"private", "no", "military"}

# MAJOR — BORROWED (OSM wiki, Key:highway; the classes that connect places)
# Outside the park boundary only these are kept: the first run of the Smokies
# took every street of Gatlinburg, Pigeon Forge and Cherokee (8,000 km, 9 MB)
# for a map that needs the approach roads and nothing else out there.
MAJOR = {"motorway", "trunk", "primary", "secondary", "tertiary",
         "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}

# NEVER — ASSUMED (parking aisles, driveways and the like route nobody anywhere)
NEVER = {"service", "living_street", "road"}

KIND_ROAD, KIND_TRAIL = 0, 1


def _query(park: Park, timeout_s: int) -> str:
    tags = "|".join(sorted(ROAD_TAGS | TRAIL_TAGS))
    return f'[out:json][timeout:{timeout_s}];way["highway"~"^({tags})$"]({park.bbox.as_overpass()});out geom;'


def simplify(coords: list[tuple[float, float]], tol_m: float) -> list[tuple[float, float]]:
    """Douglas-Peucker in metres on an equirectangular projection; fine at
    the scale of one park."""
    if len(coords) <= 2:
        return coords
    import math
    lat0 = math.radians(coords[0][1])
    kx = 111_320.0 * math.cos(lat0)
    ky = 110_540.0
    pts = [(x * kx, y * ky) for x, y in coords]

    def perp(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if dx == 0 and dy == 0:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
        return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))

    keep = [False] * len(coords)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]
    while stack:
        i, j = stack.pop()
        best, idx = 0.0, -1
        for k in range(i + 1, j):
            d = perp(pts[k], pts[i], pts[j])
            if d > best:
                best, idx = d, k
        if idx >= 0 and best > tol_m:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [c for c, k in zip(coords, keep, strict=True) if k]


def build_graph(elements: list[dict], boundary: dict | None = None) -> dict:
    """Overpass `out geom` ways -> {nodes, edges, names}. Edges end at every
    junction (a node shared by two ways), every way end, and at least every
    MAX_EDGE_M, so a site can snap to a node that is never far away. With a
    boundary, ways outside it survive only if they are MAJOR roads."""
    ways = []
    dropped_access = dropped_outside = dropped_kind = 0
    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags", {})
        hw = tags.get("highway")
        if hw not in ROAD_TAGS and hw not in TRAIL_TAGS:
            continue
        if hw in NEVER:
            dropped_kind += 1
            continue
        if tags.get("access") in NO_ACCESS or tags.get("motor_vehicle") == "private":
            dropped_access += 1
            continue
        if len(el.get("nodes", [])) != len(el.get("geometry", [])) or len(el["nodes"]) < 2:
            continue
        if boundary is not None and hw not in MAJOR:
            mid = el["geometry"][len(el["geometry"]) // 2]
            if not point_in_geometry(mid["lon"], mid["lat"], boundary["geometry"]):
                dropped_outside += 1
                continue
        ways.append(el)

    seen: dict[int, int] = {}
    for w in ways:
        for nid in w["nodes"]:
            seen[nid] = seen.get(nid, 0) + 1
    junction = {nid for nid, n in seen.items() if n >= 2}

    nodes: list[list[float]] = []
    node_idx: dict[int, int] = {}
    names: list[str] = []
    name_idx: dict[str, int] = {}
    edges: list[list] = []

    def idx_of(nid: int, lon: float, lat: float) -> int:
        i = node_idx.get(nid)
        if i is None:
            i = len(nodes)
            node_idx[nid] = i
            nodes.append([round(lon, COORD_DECIMALS), round(lat, COORD_DECIMALS)])
        return i

    for w in ways:
        tags = w.get("tags", {})
        kind = KIND_ROAD if tags["highway"] in ROAD_TAGS else KIND_TRAIL
        oneway = 1 if (tags.get("oneway") in ("yes", "1", "true") or tags.get("junction") == "roundabout") else 0
        name = tags.get("name")
        if name and name not in name_idx:
            name_idx[name] = len(names)
            names.append(name)
        n_i = name_idx[name] if name else -1
        ids, geom = w["nodes"], w["geometry"]
        seg_ids = [ids[0]]
        seg = [(geom[0]["lon"], geom[0]["lat"])]
        length = 0.0
        for k in range(1, len(ids)):
            p = (geom[k]["lon"], geom[k]["lat"])
            length += haversine_m(seg[-1][0], seg[-1][1], p[0], p[1])
            seg.append(p)
            seg_ids.append(ids[k])
            last = k == len(ids) - 1
            if last or ids[k] in junction or length >= MAX_EDGE_M:
                a = idx_of(seg_ids[0], seg[0][0], seg[0][1])
                b = idx_of(seg_ids[-1], seg[-1][0], seg[-1][1])
                if a != b and length > 0:
                    coords = [[round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)] for x, y in simplify(seg, SIMPLIFY_M)]
                    edges.append([a, b, round(length), kind, oneway, n_i, coords])
                seg_ids, seg, length = [ids[k]], [p], 0.0
    return {"nodes": nodes, "edges": edges, "names": names,
            "stats": {"ways": len(ways), "dropped_access": dropped_access, "dropped_outside": dropped_outside,
                      "dropped_kind": dropped_kind, "junctions": len(junction)}}


def build_roads(park: Park, out_dir: Path, *, timeout_s: int = 120) -> dict:
    elements = run_query(_query(park, timeout_s), timeout_s=timeout_s)
    boundary_path = out_dir / "boundary.geojson"
    boundary = json.loads(boundary_path.read_text()) if boundary_path.exists() else None
    if boundary is None:
        log.warning("%s: no boundary.geojson yet (run landmarks first); keeping every way in the bbox", park.key)
    graph = build_graph(elements, boundary)
    stats = graph.pop("stats")
    log_filter("roads.osm", "OSM highway ways: public access, no service roads, outside the boundary only major roads",
               len(elements), stats["ways"], park=park.key, **stats)
    payload = {"park": park.key, "fetched": datetime.now(UTC).isoformat(timespec="seconds"),
               "attribution": "© OpenStreetMap contributors, ODbL",
               "kinds": ["road", "trail"], "edge": ["from", "to", "length_m", "kind", "oneway", "name_index", "coords"],
               **graph}
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "roads.json"
    path.write_text(json.dumps(payload, separators=(",", ":")))
    write_park_manifest(out_dir, park.key)
    km = {"road": 0.0, "trail": 0.0}
    for e in graph["edges"]:
        km["road" if e[3] == KIND_ROAD else "trail"] += e[2] / 1000
    return {"nodes": len(graph["nodes"]), "edges": len(graph["edges"]), "road_km": round(km["road"]), "trail_km": round(km["trail"]),
            "bytes": path.stat().st_size, **stats}
