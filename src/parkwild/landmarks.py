"""Landmarks and the park boundary, for the virtual tour.

PROBLEM: a walk-through needs places to walk between (Old Faithful, Lamar
Valley, Cades Cove) and the outline of the park so the map stays inside it.
Neither is in the sightings data.

FIRST ATTEMPT: Wikipedia geosearch inside the park's bounding box. Hundreds of
creeks and minor peaks came back and nothing separated a landmark from a
tributary.

CURRENT: OpenStreetMap features inside the park that carry a `wikidata` tag
(somebody found them notable enough to link to a Wikidata item), restricted
to a handful of feature classes and fetched through Overpass; a curated,
ordered `tour` list per park in config/parks.toml names the stops, matched to
those features by name (or to a fallback coordinate when OSM has no feature,
as for a valley). Each stop's one-paragraph summary comes from Wikipedia's
REST summary endpoint. The boundary is iNaturalist's polygon for the same
place id the sightings were filtered by, so "inside the park" means the same
thing on both sides.

CONSIDERED: NPS boundary shapefiles (public domain, but one national download
for three outlines); Wikidata SPARQL "located in protected area" (sparse).

UNRESOLVED: the feature-class list was tuned on Yellowstone. The Smokies'
notable places are coves and overlooks, which OSM tags less consistently, so
that park leans harder on the curated list. Licences: OSM extracts are ODbL
(attribution on the map; the extract lives in this public repo); Wikipedia
text is CC BY-SA 4.0 and every excerpt links to its article; the iNaturalist
place polygon is shown as an outline only and credited in the data card.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from .config import Park
from .decisionlog import log_filter
from .export import write_park_manifest
from .geo import point_in_geometry
from .overpass import run_query

log = logging.getLogger(__name__)

INAT_PLACE_URL = "https://api.inaturalist.org/v1/places/{id}"
# COMMONS_API — BORROWED (Wikimedia Commons Action API endpoint)
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# PHOTO_RADIUS_M — ASSUMED (a photograph taken within this of the stop shows
# the stop; geysers and falls are photographed from their boardwalks and
# overlooks, which sit a few hundred metres off the feature's own point)
PHOTO_RADIUS_M = 400
# PHOTOS_PER_STOP — ARBITRARY (a strip, not a gallery)
PHOTOS_PER_STOP = 6
# PHOTO_CANDIDATES — ARBITRARY (Commons returns nearest first; check this many licences)
PHOTO_CANDIDATES = 16
# PHOTO_WIDTH — ARBITRARY (two columns of a 300 px card on a 2x screen)
PHOTO_WIDTH = 640
# STREET_RADIUS_M — ASSUMED (a street-level image this close to the stop looks at it or from it)
STREET_RADIUS_M = 300
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
# Wikimedia asks for a User-Agent that identifies the project and a way to reach it.
HEADERS = {"User-Agent": "parkwild/0.1 (wildlife side project; https://github.com/Tlappas-23/parkwild)"}

# KINDS — ASSUMED (what a visitor would call a landmark, keyed by OSM tag)
# Ordered by how much a tour wants them: a geyser or waterfall before a
# generic attraction, and a named place last. The order also breaks ties when
# a curated name matches more than one feature.
# REVISIT IF: a park's curated stops keep failing to match (see "missing" in
# the output) or the map fills with a class nobody taps.
KINDS: list[tuple[str, str, str]] = [   # (osm key, osm value regex, kind)
    ("natural", "geyser", "geyser"),
    ("natural", "hot_spring|spring", "hot spring"),
    ("waterway", "waterfall", "waterfall"),
    ("natural", "waterfall", "waterfall"),
    ("natural", "peak|volcano", "peak"),
    ("natural", "water|bay", "lake"),
    ("natural", "valley", "valley"),
    ("natural", "cave_entrance|arch", "rock"),
    ("mountain_pass", "yes", "pass"),
    ("tourism", "viewpoint", "viewpoint"),
    ("tourism", "information", "visitor centre"),
    ("tourism", "museum|attraction", "attraction"),
    ("historic", ".*", "historic"),
    ("place", "locality|hamlet|village|isolated_dwelling", "place"),
]

# MAX_LANDMARKS / MAX_PER_KIND — ARBITRARY (about what fits on a park map)
# Yellowstone alone has 80 geysers with a Wikidata item; the map wants a
# spread of kinds, not every geyser. Within a kind, features with a Wikipedia
# article come first, because that is the only notability signal OSM offers.
# REVISIT IF: labels collide at the default zoom, or a park has fewer than 20.
MAX_LANDMARKS = 80
MAX_PER_KIND = 20

# COORD_DECIMALS — ARBITRARY (about 10 m; a boundary with thousands of
# vertices stays small in the app bundle and no outline needs better)
COORD_DECIMALS = 4


def fetch_boundary(park: Park, *, session: requests.Session | None = None) -> dict:
    """The park outline as a GeoJSON Feature, from the iNaturalist place record."""
    s = session or requests.Session()
    resp = s.get(INAT_PLACE_URL.format(id=park.inat_place_id), headers=HEADERS, timeout=60)
    resp.raise_for_status()
    rec = resp.json()["results"][0]
    geom = rec.get("geometry_geojson")
    if not geom:
        raise RuntimeError(f"iNaturalist place {park.inat_place_id} has no geometry")
    return {
        "type": "Feature",
        "geometry": _round_geometry(geom),
        "properties": {"park": park.key, "name": park.name, "source": "iNaturalist place", "place_id": park.inat_place_id,
                       "source_url": f"https://www.inaturalist.org/places/{park.inat_place_id}"},
    }


def _round_geometry(geom: dict) -> dict:
    def rnd(coords):
        if isinstance(coords[0], (int, float)):
            return [round(coords[0], COORD_DECIMALS), round(coords[1], COORD_DECIMALS)]
        return [rnd(c) for c in coords]
    return {"type": geom["type"], "coordinates": rnd(geom["coordinates"])}


def _overpass_query(park: Park, timeout_s: int) -> str:
    box = park.bbox.as_overpass()
    parts = "".join(f'nwr["wikidata"]["{key}"~"^({values})$"]({box});' for key, values, _ in KINDS)
    return f"[out:json][timeout:{timeout_s}];({parts});out tags center;"


def _kind(tags: dict) -> tuple[int, str] | None:
    import re
    for rank, (key, values, kind) in enumerate(KINDS):
        v = tags.get(key)
        if v and re.fullmatch(values, v):
            return rank, kind
    return None


def fetch_osm_landmarks(park: Park, boundary: dict, *, timeout_s: int = 90) -> tuple[list[dict], dict]:
    """Named, Wikidata-linked features of the listed kinds inside the boundary,
    best kinds first, one entry per name."""
    elements = run_query(_overpass_query(park, timeout_s), timeout_s=timeout_s)
    out: list[dict] = []
    counts = {"fetched": len(elements), "unnamed": 0, "outside": 0, "duplicate_name": 0}
    seen: set[str] = set()
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            counts["unnamed"] += 1
            continue
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        if lat is None or not point_in_geometry(lon, lat, boundary["geometry"]):
            counts["outside"] += 1
            continue
        k = _kind(tags)
        if k is None:
            continue
        rank, kind = k
        out.append({
            "id": f"{el['type']}/{el['id']}", "name": name, "kind": kind, "rank": rank,
            "lon": round(lon, 5), "lat": round(lat, 5),
            "ele_m": _num(tags.get("ele")), "wikidata": tags.get("wikidata"),
            "url": _wikipedia_url(tags.get("wikipedia")),
        })
    out.sort(key=lambda r: (r["rank"], r["url"] is None, r["name"]))
    kept = []
    for r in out:
        key = r["name"].casefold()
        if key in seen:
            counts["duplicate_name"] += 1
            continue
        seen.add(key)
        kept.append(r)
    return kept, counts


def cap_by_kind(landmarks: list[dict], stops: list[dict]) -> tuple[list[dict], int]:
    """At most MAX_PER_KIND per kind and MAX_LANDMARKS overall, tour stops always
    kept. Runs after the tour is matched: the first version capped first and
    cut Old Faithful, the 21st geyser alphabetically, so the stop fell back
    to its visitor centre."""
    stop_ids = {s["id"] for s in stops}
    per_kind: dict[str, int] = {}
    kept: list[dict] = []
    dropped = 0
    for r in landmarks:
        if r["id"] in stop_ids:
            kept.append(r)
            continue
        if per_kind.get(r["kind"], 0) >= MAX_PER_KIND or len(kept) >= MAX_LANDMARKS + len(stop_ids):
            dropped += 1
            continue
        per_kind[r["kind"]] = per_kind.get(r["kind"], 0) + 1
        kept.append(r)
    return kept, dropped


def _num(v: str | None) -> float | None:
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def _wikipedia_url(tag: str | None) -> str | None:
    """OSM's `wikipedia` tag is "en:Old Faithful"; only English articles are used."""
    if not tag or not tag.startswith("en:"):
        return None
    return "https://en.wikipedia.org/wiki/" + tag[3:].replace(" ", "_")


def wikipedia_summary(url: str, *, session: requests.Session | None = None) -> dict | None:
    """First paragraph of the article, with the canonical page URL. Wikipedia
    text is CC BY-SA 4.0; the app prints that beside every excerpt."""
    title = url.rsplit("/wiki/", 1)[-1]
    s = session or requests.Session()
    resp = s.get(WIKIPEDIA_SUMMARY_URL.format(title=title), headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        log.warning("wikipedia summary %s -> %d", title, resp.status_code)
        return None
    j = resp.json()
    return {"extract": j.get("extract"), "url": (j.get("content_urls") or {}).get("desktop", {}).get("page", url),
            "licence": "CC BY-SA 4.0", "attribution": "Wikipedia"}


def commons_photos_near(lat: float, lon: float, *, session: requests.Session | None = None) -> list[dict]:
    """Photographs on Wikimedia Commons taken within PHOTO_RADIUS_M, kept only
    under licences that allow reuse with credit (same rule as the park cards,
    ADR-0019), nearest first."""
    from .parksindex import pick_licence
    s = session or requests.Session()
    r = s.get(COMMONS_API, params={"action": "query", "list": "geosearch", "gscoord": f"{lat}|{lon}", "gsradius": PHOTO_RADIUS_M,
                                   "gsnamespace": 6, "gslimit": PHOTO_CANDIDATES, "format": "json"}, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return []
    hits = [g for g in (r.json().get("query") or {}).get("geosearch", []) if g["title"].lower().endswith((".jpg", ".jpeg", ".png"))]
    if not hits:
        return []
    q = s.get(COMMONS_API, params={"action": "query", "titles": "|".join(g["title"] for g in hits), "prop": "imageinfo",
                                   "iiprop": "extmetadata|url|size", "iiurlwidth": PHOTO_WIDTH, "format": "json"}, headers=HEADERS, timeout=30)
    if q.status_code != 200:
        return []
    pages = {p.get("title"): p for p in ((q.json().get("query") or {}).get("pages") or {}).values()}
    out = []
    for g in hits:
        info = (pages.get(g["title"], {}).get("imageinfo") or [{}])[0]
        lic = pick_licence(info.get("extmetadata") or {})
        if lic is None or not info.get("thumburl"):
            continue
        # The API answers with thumb.wikimedia.org; the same path is served from
        # upload.wikimedia.org, the host the page's content-security policy allows.
        url = info["thumburl"].replace("https://thumb.wikimedia.org/", "https://upload.wikimedia.org/").split("?")[0]
        out.append({"url": url, "page": info.get("descriptionurl", ""), "dist_m": round(g["dist"]),
                    "width": info.get("thumbwidth"), "height": info.get("thumbheight"), **lic})
        if len(out) >= PHOTOS_PER_STOP:
            break
    return out


def nearest_street_image(lat: float, lon: float, *, client=None) -> dict | None:
    """The closest Mapillary image to the stop (a panorama if one is as close),
    kept as an id and a credit; the app links to Mapillary, it never copies
    the picture. Needs the pipeline's token; without one, nothing."""
    from .config import mapillary_token
    from .geo import BBox, haversine_m
    from .mapillary import MapillaryClient, image_page_url
    try:
        token = mapillary_token()
    except Exception:
        return None
    if not token:
        return None
    c = client or MapillaryClient(token)
    d = STREET_RADIUS_M / 111_320.0
    box = BBox(lon - d, lat - d * 0.72, lon + d, lat + d * 0.72)
    try:
        recs = c.search_images(box, fields=("id", "captured_at", "is_pano", "creator", "computed_geometry", "geometry"), limit=100)
    except Exception as exc:                                  # a stop without imagery is not an error
        log.info("mapillary lookup failed at %.4f,%.4f: %s", lat, lon, exc)
        return None
    best = None
    for rec in recs:
        g = (rec.get("computed_geometry") or rec.get("geometry") or {}).get("coordinates")
        if not g:
            continue
        dist = haversine_m(lon, lat, g[0], g[1])
        if dist > STREET_RADIUS_M:
            continue
        score = dist - (150 if rec.get("is_pano") else 0)      # a panorama wins unless a flat frame is much closer
        if best is None or score < best[0]:
            creator = rec.get("creator") or {}
            cap = rec.get("captured_at")
            # The Graph API returns capture time as epoch milliseconds.
            when = datetime.fromtimestamp(cap / 1000, UTC).date().isoformat() if isinstance(cap, (int, float)) else (str(cap)[:10] or None) if cap else None
            best = (score, {"image_id": str(rec["id"]), "username": creator.get("username") if isinstance(creator, dict) else None,
                            "captured_at": when, "is_pano": bool(rec.get("is_pano")),
                            "dist_m": round(dist), "url": image_page_url(str(rec["id"])), "license": "CC BY-SA 4.0"})
    return best[1] if best else None


def match_tour(park: Park, landmarks: list[dict]) -> tuple[list[dict], list[str]]:
    """Curated stop names -> landmark records, in tour order. Exact name match
    first, then a landmark whose name starts with or contains the stop name;
    a configured fallback coordinate when OSM has nothing; otherwise reported
    as missing so the config can be fixed rather than the stop silently lost."""
    by_name = {r["name"].casefold(): r for r in landmarks}
    stops: list[dict] = []
    missing: list[str] = []
    for i, name in enumerate(park.tour):
        key = name.casefold()
        hit = by_name.get(key)
        # A configured coordinate is deliberate, so it beats a fuzzy match: on
        # the first run "Norris Geyser Basin" matched the Norris Geyser Basin
        # Museum by prefix and the stop's summary was about a building.
        if hit is None and name in park.tour_fallback:
            lon, lat = park.tour_fallback[name]
            hit = {"id": f"config/{i}", "name": name, "kind": "place", "rank": len(KINDS), "lon": lon, "lat": lat,
                   "ele_m": None, "wikidata": None, "url": "https://en.wikipedia.org/wiki/" + name.replace(" ", "_")}
            landmarks.append(hit)
        if hit is None:
            cands = [r for r in landmarks if r["name"].casefold().startswith(key)] or \
                    [r for r in landmarks if key in r["name"].casefold()]
            hit = cands[0] if cands else None
        if hit is None:
            missing.append(name)
            continue
        if name in park.tour_wiki:
            hit["url"] = "https://en.wikipedia.org/wiki/" + park.tour_wiki[name]
        hit["tour"] = len(stops)
        stops.append(hit)
    return stops, missing


# AUTO_TOUR_STOPS — ARBITRARY (a morning's drive; the curated lists run 8 to 11)
AUTO_TOUR_STOPS = 8


def auto_tour(landmarks: list[dict]) -> list[dict]:
    """Stops for a park nobody has curated yet: landmarks with a Wikipedia
    article, one of each kind first (a visitor centre, a peak, a lake, a
    waterfall…) then the rest by kind rank, capped at AUTO_TOUR_STOPS and
    ordered as a nearest-neighbour chain from the westernmost, which is a
    fair stand-in for "drive through". Curated lists in config/parks.toml
    always win; this only fills the gap so every park has a tour."""
    with_article = [r for r in landmarks if r.get("url")]
    picked: list[dict] = []
    seen_kinds: set[str] = set()
    for r in with_article:
        if r["kind"] not in seen_kinds:
            picked.append(r)
            seen_kinds.add(r["kind"])
    for r in with_article:
        if len(picked) >= AUTO_TOUR_STOPS:
            break
        if r not in picked:
            picked.append(r)
    picked = picked[:AUTO_TOUR_STOPS]
    if not picked:
        return []
    from .geo import haversine_m
    order = [min(picked, key=lambda r: r["lon"])]
    rest = [r for r in picked if r is not order[0]]
    while rest:
        cur = order[-1]
        nxt = min(rest, key=lambda r: haversine_m(cur["lon"], cur["lat"], r["lon"], r["lat"]))
        order.append(nxt)
        rest.remove(nxt)
    for i, r in enumerate(order):
        r["tour"] = i
    return order


def build_landmarks(park: Park, out_dir: Path, *, summaries: bool = True) -> dict:
    """Fetch, match, summarise, write boundary.geojson + landmarks.json, rehash the manifest."""
    session = requests.Session()
    boundary = fetch_boundary(park, session=session)
    landmarks, counts = fetch_osm_landmarks(park, boundary)
    stops, missing = match_tour(park, landmarks)
    auto = False
    if not park.tour:
        stops, auto = auto_tour(landmarks), True
    landmarks, counts["over_kind_cap"] = cap_by_kind(landmarks, stops)
    log_filter("landmarks.osm", "named, wikidata-tagged OSM features of the listed kinds inside the park boundary, capped per kind",
               counts["fetched"], len(landmarks), park=park.key, **{k: v for k, v in counts.items() if k != "fetched"})
    if missing:
        log.warning("%s: tour stops not found in OSM: %s", park.key, missing)
    if summaries:
        for stop in stops:
            if stop.get("url"):
                stop["summary"] = wikipedia_summary(stop["url"], session=session)
                time.sleep(1.0)     # Wikimedia etiquette: one request a second is plenty for a dozen stops
            # What the place actually looks like: licensed photographs taken
            # there, and the nearest street-level image to look around from.
            stop["photos"] = commons_photos_near(stop["lat"], stop["lon"], session=session)
            time.sleep(0.5)
            stop["street"] = nearest_street_image(stop["lat"], stop["lon"])
    payload = {
        "park": park.key, "fetched": datetime.now(UTC).isoformat(timespec="seconds"),
        "attribution": {"landmarks": "© OpenStreetMap contributors, ODbL", "summaries": "Wikipedia, CC BY-SA 4.0",
                        "boundary": f"iNaturalist place {park.inat_place_id}"},
        "landmarks": [{k: v for k, v in r.items() if k != "rank"} for r in landmarks],
        "tour": [s["id"] for s in stops],
        "tour_source": "auto" if auto else "curated",
        "missing_stops": missing,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "boundary.geojson").write_text(json.dumps(boundary, separators=(",", ":")))
    (out_dir / "landmarks.json").write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    write_park_manifest(out_dir, park.key)
    return {"landmarks": len(landmarks), "stops": len(stops), "tour_source": "auto" if auto else "curated", "missing": missing, "osm": counts,
            "stop_photos": sum(len(s.get("photos") or []) for s in stops), "stops_with_street": sum(1 for s in stops if s.get("street")),
            "boundary_bytes": (out_dir / "boundary.geojson").stat().st_size,
            "landmarks_bytes": (out_dir / "landmarks.json").stat().st_size}
