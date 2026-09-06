"""Places: every named trail, site, viewpoint, campground and facility in a
park, with what people recorded within reach of it: places.json.

The owner wanted the trails and sites of a park sorted by how popular they
are, with the best times to see them, and a page for each like the species
pages. Nobody publishes visitor counts per trail for free, so the measure
here is the one this project already has: how many sightings people recorded
within reach of the place (500 m of a point, 300 m of a trail), which species,
and in which months. That is where observers went and when, which is the
best free proxy for where visitors go. Landmarks with a Wikipedia article
also carry the article's average monthly readers from the Wikimedia
pageviews API, free and keyless, as a second, independent signal.

Inputs are the park's own exported files, so this runs without the database:
landmarks.json (with summaries and photographs), amenities.json (items and
trails), roads.json (trail geometry), sightings.parquet (open coordinates
only; obscured records are never placed). The output lists places by
sightings within reach, most first.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

import duckdb
import requests

from .config import EXPORT_DIR, Park
from .decisionlog import log_filter
from .export import write_park_manifest

log = logging.getLogger(__name__)

# POINT_RADIUS_M — ASSUMED (a site's surroundings: the car park, the overlook and the ground it looks at)
POINT_RADIUS_M = 500
# TRAIL_BUFFER_M — ASSUMED (how far off a trail a recorded sighting still belongs to it; the app uses the same)
TRAIL_BUFFER_M = 300
# TRAIL_SAMPLE_M — ARBITRARY (a point every this far along a trail stands in for the line in the distance test)
TRAIL_SAMPLE_M = 150
# TOP_SPECIES — ARBITRARY (species kept per place; the page shows these with a photograph each)
TOP_SPECIES = 5
# PAGEVIEWS_URL — BORROWED (Wikimedia REST API: monthly readers of an article, free, no key)
PAGEVIEWS_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{title}/monthly/{start}/{end}"
# PAGEVIEWS_PAUSE_S — ARBITRARY (well under the API's published rate limit)
PAGEVIEWS_PAUSE_S = 0.15
# EARTH_RADIUS_M — MEASURED (mean Earth radius)
EARTH_RADIUS_M = 6_371_000
# M_PER_DEG_LAT — DERIVED (metres per degree of latitude)
M_PER_DEG_LAT = 111_320
USER_AGENT = "parkwild/1.0 (https://github.com/Tlappas-23/parkwild)"


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def trail_geometry(roads: dict, name: str) -> list[list[list[float]]]:
    """Every edge of the graph carrying this name, as coordinate lists."""
    idx = roads["names"].index(name) if name in roads["names"] else -1
    if idx < 0:
        return []
    return [e[6] for e in roads["edges"] if e[5] == idx and e[6]]


def sample_lines(lines: list[list[list[float]]], step_m: float = TRAIL_SAMPLE_M) -> list[tuple[float, float]]:
    """A point every step_m along each line, plus every line's first point."""
    out: list[tuple[float, float]] = []
    for line in lines:
        if not line:
            continue
        out.append((line[0][0], line[0][1]))
        since = 0.0
        for a, b in zip(line, line[1:]):
            seg = haversine_m(a[0], a[1], b[0], b[1])
            since += seg
            while since >= step_m and seg > 0:
                since -= step_m
                f = 1 - since / seg if seg else 1
                out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


def collect_places(landmarks: dict | None, amenities: dict | None, roads: dict | None) -> tuple[list[dict], dict]:
    """Landmarks first (they carry summaries and photographs), then named items,
    then trails; one entry per OSM id. Unnamed items are dropped: a list of
    forty 'Campsite' rows helps nobody."""
    places: list[dict] = []
    seen: set[str] = set()
    counts = {"landmarks": 0, "items_named": 0, "items_unnamed": 0, "trails": 0, "duplicates": 0}
    for lm in (landmarks or {}).get("landmarks", []):
        if lm["id"] in seen:
            counts["duplicates"] += 1
            continue
        seen.add(lm["id"])
        places.append({"id": lm["id"], "src": "landmark", "kind": lm["kind"], "name": lm["name"], "lon": lm["lon"], "lat": lm["lat"],
                       "ele_m": lm.get("ele_m"), "url": lm.get("url"), "samples": [(lm["lon"], lm["lat"])], "r": POINT_RADIUS_M})
        counts["landmarks"] += 1
    for it in (amenities or {}).get("items", []):
        if not it.get("named"):
            counts["items_unnamed"] += 1
            continue
        if it["id"] in seen:
            counts["duplicates"] += 1
            continue
        seen.add(it["id"])
        tags = {k: v for k, v in (it.get("tags") or {}).items() if k in ("fee", "reservation", "ele", "description", "website", "opening_hours")}
        places.append({"id": it["id"], "src": "item", "kind": it["kind"], "sub": it.get("sub"), "name": it["name"], "lon": it["lon"], "lat": it["lat"],
                       "ele_m": float(tags["ele"]) if tags.get("ele", "").replace(".", "", 1).isdigit() else None, "tags": tags or None,
                       "samples": [(it["lon"], it["lat"])], "r": POINT_RADIUS_M})
        counts["items_named"] += 1
    for tr in (amenities or {}).get("trails", []):
        if tr["id"] in seen:
            counts["duplicates"] += 1
            continue
        seen.add(tr["id"])
        lines = trail_geometry(roads, tr["name"]) if roads else []
        samples = sample_lines(lines) if lines else [(tr["lon"], tr["lat"])]
        places.append({"id": tr["id"], "src": "trail", "kind": "trail", "name": tr["name"], "lon": tr["lon"], "lat": tr["lat"],
                       "length_m": tr.get("length_m"), "samples": samples, "r": TRAIL_BUFFER_M})
        counts["trails"] += 1
    return places, counts


def sightings_near(parquet: Path, places: list[dict]) -> dict[int, dict]:
    """Per place: sightings within reach, by month and species. One in-memory
    DuckDB over the park's parquet; a bounding-box join first, the exact
    distance after, each sighting counted once per place however many trail
    samples it is near."""
    con = duckdb.connect()
    con.execute("CREATE TABLE s AS SELECT sighting_id, lon, lat, month(observed_on) AS m, scientific_name, common_name "
                "FROM read_parquet(?) WHERE coordinate_status = 'open' AND lon IS NOT NULL AND lat IS NOT NULL", [str(parquet)])
    con.execute("CREATE TABLE p (pid INTEGER, lon DOUBLE, lat DOUBLE, r DOUBLE)")
    rows = [(i, lon, lat, float(pl["r"])) for i, pl in enumerate(places) for lon, lat in pl["samples"]]
    if rows:
        con.executemany("INSERT INTO p VALUES (?, ?, ?, ?)", rows)
    q = f"""
    WITH hit AS (
      SELECT DISTINCT p.pid, s.sighting_id, s.m, s.scientific_name, s.common_name
      FROM p JOIN s
        ON s.lat BETWEEN p.lat - p.r / {M_PER_DEG_LAT} AND p.lat + p.r / {M_PER_DEG_LAT}
       AND s.lon BETWEEN p.lon - p.r / ({M_PER_DEG_LAT} * cos(radians(p.lat))) AND p.lon + p.r / ({M_PER_DEG_LAT} * cos(radians(p.lat)))
      WHERE 2 * {EARTH_RADIUS_M} * asin(sqrt(pow(sin(radians(s.lat - p.lat) / 2), 2)
            + cos(radians(p.lat)) * cos(radians(s.lat)) * pow(sin(radians(s.lon - p.lon) / 2), 2))) <= p.r
    )
    SELECT pid, m, scientific_name, any_value(common_name), count(*) FROM hit GROUP BY pid, m, scientific_name
    """
    out: dict[int, dict] = {}
    for pid, m, sci, common, n in con.execute(q).fetchall():
        rec = out.setdefault(pid, {"n": 0, "months": [0] * 12, "species": {}})
        rec["n"] += n
        if m:
            rec["months"][int(m) - 1] += n
        sp = rec["species"].setdefault(sci, [common, 0])
        sp[1] += n
        if not sp[0] and common:
            sp[0] = common
    con.close()
    return out


def wikipedia_views(url: str, *, session: requests.Session, today: date | None = None) -> int | None:
    """Average monthly readers over the last twelve complete months, or None."""
    if "/wiki/" not in url:
        return None
    title = unquote(url.split("/wiki/", 1)[1]).replace(" ", "_")
    today = today or date.today()
    end = today.replace(day=1) - timedelta(days=1)                       # last day of the previous month
    y, m = end.year, end.month - 11                                        # eleven months back: twelve complete months
    start = date(y - 1, m + 12, 1) if m <= 0 else date(y, m, 1)
    try:
        r = session.get(PAGEVIEWS_URL.format(title=requests.utils.quote(title, safe=""), start=start.strftime("%Y%m01"), end=end.strftime("%Y%m%d")),
                        headers={"User-Agent": USER_AGENT}, timeout=20)
        if r.status_code != 200:
            return None
        items = r.json().get("items", [])
        if not items:
            return None
        return round(sum(i.get("views", 0) for i in items) / len(items))
    except (requests.RequestException, ValueError):
        return None


def build_places(park: Park, out_dir: Path | None = None, *, views: bool = True, session: requests.Session | None = None) -> dict:
    out_dir = out_dir or EXPORT_DIR / park.key
    read = lambda name: json.loads((out_dir / name).read_text()) if (out_dir / name).exists() else None  # noqa: E731
    landmarks, amenities, roads = read("landmarks.json"), read("amenities.json"), read("roads.json")
    places, counts = collect_places(landmarks, amenities, roads)
    log_filter("places.named", "landmarks, named amenities and trails kept; unnamed items dropped; one entry per OSM id",
               counts["landmarks"] + counts["items_named"] + counts["items_unnamed"] + counts["trails"] + counts["duplicates"], len(places))
    parquet = out_dir / "sightings.parquet"
    near = sightings_near(parquet, places) if parquet.exists() else {}
    session = session or requests.Session()
    fetched_views = 0
    for i, pl in enumerate(places):
        rec = near.get(i, {"n": 0, "months": [0] * 12, "species": {}})
        top = sorted(rec["species"].items(), key=lambda kv: (-kv[1][1], kv[0]))[:TOP_SPECIES]
        # the top species as [scientific name, count]; the app knows the common names from species.json
        pl["near"] = {"n": rec["n"], "species": len(rec["species"]), "top": [[sci, n] for sci, (_common, n) in top], "months": rec["months"]}
        if views and pl.get("url"):
            pl["views_pm"] = wikipedia_views(pl["url"], session=session)
            fetched_views += pl["views_pm"] is not None
            time.sleep(PAGEVIEWS_PAUSE_S)
        pl.pop("samples", None)
        pl.pop("r", None)
    places.sort(key=lambda p: (-p["near"]["n"], p["name"]))
    payload = {
        "park": park.key, "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "point_radius_m": POINT_RADIUS_M, "trail_buffer_m": TRAIL_BUFFER_M,
        "attribution": "Places: OpenStreetMap contributors (ODbL). Readers: Wikimedia pageviews API. Sightings: iNaturalist and GBIF, open coordinates only.",
        "notes": {"popularity": "Sightings people recorded within reach of the place: where observers went, "
                                "the free proxy for where visitors go. Not a visitor count.",
                  "months": "Sightings by month within reach; reflects when people looked as much as when animals were there."},
        "places": places,
    }
    (out_dir / "places.json").write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    write_park_manifest(out_dir, park.key)
    return {"places": len(places), "with_sightings": sum(1 for p in places if p["near"]["n"]), "views_fetched": fetched_views,
            "bytes": (out_dir / "places.json").stat().st_size, **counts}
