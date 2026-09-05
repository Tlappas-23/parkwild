"""Mapillary Graph API v4 client and crawler.

PROBLEM: enumerate every image in a corridor without missing any, under an API
that caps a bbox search at 2000 rows, allows no paging on bbox searches, and
rejects tiles over 0.01 deg².

FIRST ATTEMPT (E-001): tile at 0.05 deg and trust `len(rows) < 2000` to mean
"got everything". Lamar Valley came back with 16,901 images. A second pass
with two more splits said 21,632. Measured directly: tiles returning 1879,
1929, 1938 and 1973 rows had quarters summing to 2559 to 3371 rows, while
tiles at 1849 and below matched their quarters. The documented limit is
applied loosely; "fewer than 2000" does not mean complete. Kept as
`is_capped_v1` with a test that pins those measurements.

SECOND FAILURE (E-002): two 0.05 deg tiles in Cades Cove answered HTTP 500 at
any `limit`; their quarters answered normally. A dense tile is refused, not
truncated.

CURRENT: treat >= CAP_SUSPECT_ROWS (1500) as "probably capped" and quarter the
tile; treat a repeated 5xx on a splittable tile as "too heavy" and quarter it;
mark an unsplittable error tile `error` so the next run retries it. Lamar:
27,430 images from 101 tile queries, zero truncated leaves.

CONSIDERED, NOT DONE: `mapillary-python-sdk` (hides exactly the behaviour
above); the vector-tile coverage endpoint (a different rate-limit tier, and
it returns tile geometry, not image metadata).

UNRESOLVED: why parent tiles occasionally return a few more rows than their
quarters combined (1573 vs 1513 in one Lamar tile). Dedupe by image id makes
it harmless; the cause is probably a coarse spatial index returning fringe
images. Not chased.
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import requests

from .config import MAPILLARY_LICENSE
from .geo import DEFAULT_TILE_DEG, BBox, tile_bbox

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.mapillary.com"

# SEARCH_LIMIT — BORROWED (API docs: "Max and default is 2000")
# The value sent as `limit`. Sending less would only make truncation more
# likely; the server's own cap is fuzzy anyway (see CAP_SUSPECT_ROWS).
SEARCH_LIMIT = 2000

# CAP_SUSPECT_ROWS — MEASURED (2026-09-05, Lamar Valley, 9 dense tiles)
#
# Parent-tile rows vs sum of its four quarters:
#     1573 -> 1513   complete (fringe effect, see UNRESOLVED)
#     1604 -> 1604   complete
#     1849 -> 1849   complete
#     1879 -> 2559   TRUNCATED
#     1929 -> 2771   TRUNCATED
#     1938 -> 2847   TRUNCATED
#     1973 -> 3371   TRUNCATED
#     2000 -> 3165   TRUNCATED
#     2000 -> 5417   TRUNCATED
#
# Lowest truncation seen: 1879. 1500 leaves a wide margin. Cost of being too
# low is a few extra queries; cost of being too high is silent under-counting.
# REJECTED: 2000 (the documented cap): under-counted Lamar by a third.
# REVISIT IF: a tile between 1500 and 1849 is ever shown to be truncated, or
#   Mapillary documents the real behaviour.
CAP_SUSPECT_ROWS = 1500

# MIN_SPLIT_TILE_DEG — ASSUMED
# Below this width (~160 m at 45 N) a tile with 1500+ images is a parking lot
# or a bug, not a road, and recursion stops with the tile marked `capped`.
# Never reached in three corridors.
# REVISIT IF: a `capped` tile ever appears in the tiles table.
MIN_SPLIT_TILE_DEG = 0.002

# MIN_INTERVAL_S — ARBITRARY
# Documented rate limit is 10,000 search calls/min per app; this client makes
# at most ~7/s. The pause is politeness, not necessity.
MIN_INTERVAL_S = 0.15

# MAX_RETRIES — ARBITRARY
# Exponential backoff 2^n s capped at 60 s, so 6 retries is about two minutes
# of patience per call before giving up. Crawls use a smaller budget per tile
# (tile_retries) because a heavy tile should fail fast and split.
MAX_RETRIES = 6

# The metadata kept for every image. Names confirmed against the docs' field
# list. `computed_*` are Mapillary's structure-from-motion corrections and
# can be null on images that haven't been processed.
IMAGE_FIELDS: tuple[str, ...] = (
    "id", "geometry", "computed_geometry", "captured_at", "compass_angle", "computed_compass_angle",
    "camera_type", "is_pano", "make", "model", "width", "height", "quality_score", "sequence", "creator",
    "thumb_1024_url", "thumb_2048_url", "thumb_original_url",
)

# Cheapest field set for a counting pass: enough for image count, date range
# and distinct sequences without pulling thumbnail URLs for every image.
COVERAGE_FIELDS: tuple[str, ...] = ("id", "captured_at", "sequence")

# MAPILLARY_DETECTIONS_FIELD — BORROWED (docs: `detections.value`)
# Mapillary's own segmentation labels, e.g. "animal--ground-animal". Not relied
# on; a free in-domain pre-filter worth measuring (EXPERIMENTS.md Q-4).
MAPILLARY_DETECTIONS_FIELD = "detections.value"


class MapillaryError(RuntimeError):
    pass


class MapillaryAuthError(MapillaryError):
    pass


class MapillaryServerError(MapillaryError):
    """Raised after the retry budget is spent on 429 / 5xx / network errors."""


# ---- completeness rules: the superseded one first, then the current one -----------

def is_capped_v1(n_rows: int) -> bool:
    """SUPERSEDED 2026-09-05 by is_capped(). Kept for comparison.

    Trusted the documented limit: a tile is complete unless it returns exactly
    SEARCH_LIMIT rows. Under-counted Lamar Valley by a third (E-001) because
    the server truncates below 2000 without saying so. tests/test_mapillary.py::
    test_v1_cap_rule_undercounts pins the measured tiles and fails if this
    rule ever catches them.
    """
    return n_rows >= SEARCH_LIMIT


def is_capped(n_rows: int) -> bool:
    """A tile is suspected incomplete at CAP_SUSPECT_ROWS or more rows."""
    return n_rows >= CAP_SUSPECT_ROWS


@dataclass
class TileResult:
    """What `crawl()` yields for each tile it finished querying."""

    tile: BBox
    records: list[dict] = field(default_factory=list)
    hit_cap: bool = False       # in the cap zone: there may be more
    split: bool = False         # subdivided; its children will be crawled too
    error: str | None = None    # server gave up on this tile and it could not be split

    @property
    def status(self) -> str:
        if self.split:
            return "split"
        if self.error:
            return "error"
        return "capped" if self.hit_cap else "done"


class MapillaryClient:
    def __init__(
        self,
        token: str,
        *,
        min_interval_s: float = MIN_INTERVAL_S,
        max_retries: int = MAX_RETRIES,
        timeout_s: float = 60,
        session: requests.Session | None = None,
    ) -> None:
        self._session = session or requests.Session()
        # Header, not query string: the docs prefer it for entity/search calls
        # and it keeps the token out of URLs and therefore out of logs.
        self._session.headers["Authorization"] = f"OAuth {token}"
        self._session.headers["User-Agent"] = "parkwild/0.0.1 (wildlife side project; contact via Mapillary profile)"
        self._min_interval = min_interval_s
        self._max_retries = max_retries
        self._timeout = timeout_s
        self._last_call = 0.0
        self._lock = threading.Lock()   # the downloader calls get_image() from threads

    # ---- crawl -----------------------------------------------------------------

    def crawl(
        self,
        bbox: BBox,
        *,
        fields: Sequence[str] = IMAGE_FIELDS,
        tile_deg: float = DEFAULT_TILE_DEG,
        skip_tile_ids: frozenset[str] | set[str] = frozenset(),
        tile_retries: int = 2,
        **filters: str,
    ) -> Iterator[TileResult]:
        """Enumerate every image in `bbox` by walking a grid of tiles.

        A tile in the cap zone is quartered and its children pushed onto the
        work stack. So is a tile the server keeps answering with 5xx: in
        practice that means "too many images in here", and the quarters come
        back fine. `tile_retries` is kept small so a heavy tile fails fast
        instead of sitting through two minutes of backoff. `skip_tile_ids`
        carries the tiles a previous run finished, so a crawl resumes.
        """
        stack: list[BBox] = list(reversed(tile_bbox(bbox, tile_deg)))
        while stack:
            tile = stack.pop()
            if tile.tile_id in skip_tile_ids:
                continue
            can_split = tile.width_deg > MIN_SPLIT_TILE_DEG and tile.height_deg > MIN_SPLIT_TILE_DEG
            try:
                records = self.search_images(tile, fields=fields, retries=tile_retries, **filters)
            except MapillaryServerError as exc:
                if can_split:
                    log.info("tile %s: server error, treating as too heavy; splitting", tile.tile_id)
                    stack.extend(reversed(tile.split()))
                    yield TileResult(tile, [], split=True, error=str(exc))
                else:
                    log.error("tile %s: server error at minimum size; skipping: %s", tile.tile_id, exc)
                    yield TileResult(tile, [], error=str(exc))
                continue
            hit_cap = is_capped(len(records))
            if hit_cap and can_split:
                log.info("tile %s returned %d rows (cap zone); splitting", tile.tile_id, len(records))
                stack.extend(reversed(tile.split()))
                yield TileResult(tile, records, hit_cap=True, split=True)
            else:
                if hit_cap:
                    log.warning("tile %s in the cap zone at minimum size; coverage there is truncated", tile.tile_id)
                yield TileResult(tile, records, hit_cap=hit_cap, split=False)

    # ---- endpoints -------------------------------------------------------------

    def search_images(
        self,
        bbox: BBox,
        *,
        fields: Sequence[str] = IMAGE_FIELDS,
        limit: int = SEARCH_LIMIT,
        retries: int | None = None,
        **filters: str,
    ) -> list[dict]:
        """One /images search inside `bbox`. Extra keyword args become query
        filters (e.g. is_pano="false", start_captured_at="2020-01-01T00:00:00Z")."""
        if not bbox.fits_mapillary():
            raise ValueError(f"bbox area {bbox.area_deg2:.4f} deg² is over Mapillary's 0.01 limit; tile it first")
        params = {"bbox": bbox.as_mapillary(), "fields": ",".join(fields), "limit": limit, **filters}
        data = self._get("/images", params, retries=retries)
        return data.get("data", [])

    def get_image(self, image_id: str, *, fields: Sequence[str] = IMAGE_FIELDS) -> dict:
        """Entity lookup for one image. Used to refresh expired thumbnail URLs."""
        return self._get(f"/{image_id}", {"fields": ",".join(fields)})

    # ---- transport -------------------------------------------------------------

    def _get(self, path: str, params: dict, *, retries: int | None = None) -> dict:
        """GET with throttling and exponential backoff. 4xx other than 429 are
        this code's mistake and raised immediately with the server's message."""
        url = f"{GRAPH_URL}{path}"
        max_retries = self._max_retries if retries is None else retries
        for attempt in range(max_retries + 1):
            self._throttle()
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                log.warning("request error (%s), attempt %d: %s", path, attempt, exc)
                self._backoff(attempt)
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (401, 403):
                raise MapillaryAuthError(f"{resp.status_code} from Mapillary; check MAPILLARY_TOKEN: {resp.text[:300]}")
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning("HTTP %d from %s, attempt %d; backing off", resp.status_code, path, attempt)
                self._backoff(attempt)
                continue
            raise MapillaryError(f"HTTP {resp.status_code} for {path} {params}: {resp.text[:500]}")
        raise MapillaryServerError(f"gave up on {path} {params} after {max_retries} retries")

    def _throttle(self) -> None:
        with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(60.0, 2.0**attempt) + random.uniform(0, 1))


# ---- record shaping ----------------------------------------------------------------

def flatten_image(rec: dict, corridor: str | None = None) -> dict:
    """One raw API record -> one `images` row.

    Position prefers `computed_geometry` (SfM-corrected) over the raw GPS
    `geometry`; both are kept so the disagreement can be measured later. The
    raw record is stored as JSON so nothing the API returned is lost if the
    columns change.
    """
    c_lon, c_lat = _point(rec.get("computed_geometry"))
    r_lon, r_lat = _point(rec.get("geometry"))
    if c_lon is not None:
        lon, lat, position_source = c_lon, c_lat, "computed"
    else:
        lon, lat, position_source = r_lon, r_lat, "gps"

    captured_ms = rec.get("captured_at")
    captured_at = (
        datetime.fromtimestamp(captured_ms / 1000, tz=UTC).replace(tzinfo=None)
        if captured_ms is not None
        else None
    )
    creator = rec.get("creator") or {}
    detections = rec.get("detections")
    if isinstance(detections, dict):   # entity responses wrap the list in {"data": [...]}
        detections = detections.get("data")

    return {
        "image_id": str(rec["id"]),
        "corridor": corridor,
        "lon": lon,
        "lat": lat,
        "lon_raw": r_lon,
        "lat_raw": r_lat,
        "position_source": position_source,
        "captured_at_ms": captured_ms,
        "captured_at": captured_at,
        "compass_angle": rec.get("compass_angle"),
        "computed_compass_angle": rec.get("computed_compass_angle"),
        "camera_type": rec.get("camera_type"),
        "is_pano": rec.get("is_pano"),
        "make": rec.get("make"),
        "model": rec.get("model"),
        "width": rec.get("width"),
        "height": rec.get("height"),
        "quality_score": rec.get("quality_score"),
        "sequence_id": rec.get("sequence"),
        "creator_id": str(creator["id"]) if creator.get("id") is not None else None,
        "creator_username": creator.get("username"),
        "license": MAPILLARY_LICENSE,
        "source_url": image_page_url(str(rec["id"])),
        "thumb_1024_url": rec.get("thumb_1024_url"),
        "thumb_2048_url": rec.get("thumb_2048_url"),
        "thumb_original_url": rec.get("thumb_original_url"),
        "mapillary_detections": json.dumps(detections, separators=(",", ":")) if detections is not None else None,
        "raw_json": json.dumps(rec, separators=(",", ":")),
    }


# ---- pure helpers ---------------------------------------------------------------------

def image_page_url(image_id: str) -> str:
    """The Mapillary page for an image: the link attribution points at."""
    return f"https://www.mapillary.com/app/?pKey={image_id}"


def _point(geojson: dict | None) -> tuple[float | None, float | None]:
    if not geojson or geojson.get("type") != "Point":
        return None, None
    coords = geojson.get("coordinates") or []
    if len(coords) < 2:
        return None, None
    return float(coords[0]), float(coords[1])
