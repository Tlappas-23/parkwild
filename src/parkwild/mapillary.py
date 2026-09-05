"""
Thin client for the Mapillary Graph API (v4).

What it does and why:

- Sends the client token as an `Authorization: OAuth <token>` header. The docs
  call that the preferred method for entity/search calls, and it keeps the token
  out of URLs and therefore out of logs.
- Enforces the two constraints I verified against the docs on 2026-09-05:
    1. a bbox search must cover < 0.01 deg^2, so callers tile with geo.tile_bbox();
    2. pagination (`after` cursor) only works together with `creator_username`.
       For a plain bbox search the cap is 2000 results and there is no page two.
       The only way to see everything in a busy tile is to split it and query the
       quarters, which `crawl()` does automatically.
- Rate-limits politely. The documented cap for search calls is 10,000/min per app;
  I sleep a fixed minimum between requests and back off with jitter on 429 / 5xx.
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, Sequence

import requests

from .config import MAPILLARY_LICENSE
from .geo import DEFAULT_TILE_DEG, BBox, tile_bbox

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.mapillary.com"
SEARCH_LIMIT = 2000  # documented max and default for /images

# Below this tile width I stop splitting. 0.002 deg is ~160 m at 45 N; if a box
# that small still has 2000+ images it is a parking lot or a bug, not a road, and
# the crawl marks it "capped" instead of recursing forever.
MIN_SPLIT_TILE_DEG = 0.002

# The metadata I keep for every image. Names confirmed against the field list in
# the API docs. The `computed_*` values are Mapillary's structure-from-motion
# corrections and can be null on images that haven't been processed.
IMAGE_FIELDS: tuple[str, ...] = (
    "id",
    "geometry",
    "computed_geometry",
    "captured_at",
    "compass_angle",
    "computed_compass_angle",
    "camera_type",
    "is_pano",
    "make",
    "model",
    "width",
    "height",
    "quality_score",
    "sequence",
    "creator",
    "thumb_1024_url",
    "thumb_2048_url",
    "thumb_original_url",
)

# Cheapest field set for a counting pass: enough to get image count, date range
# and distinct sequences without pulling thumbnail URLs for every image.
COVERAGE_FIELDS: tuple[str, ...] = ("id", "captured_at", "sequence")

# Mapillary runs its own segmentation model over uploads; `detections.value`
# carries labels like "animal--ground-animal". I don't rely on it, but it is a
# free pre-filter worth measuring, so `pull --with-mapillary-detections` asks for it.
MAPILLARY_DETECTIONS_FIELD = "detections.value"


class MapillaryError(RuntimeError):
    pass


class MapillaryAuthError(MapillaryError):
    pass


@dataclass
class TileResult:
    """What `crawl()` yields for each tile it finished querying."""

    tile: BBox
    records: list[dict] = field(default_factory=list)
    hit_cap: bool = False  # came back with SEARCH_LIMIT rows: there may be more
    split: bool = False    # I subdivided it; its children will be crawled too

    @property
    def status(self) -> str:
        if self.split:
            return "split"
        return "capped" if self.hit_cap else "done"


class MapillaryClient:
    def __init__(
        self,
        token: str,
        *,
        min_interval_s: float = 0.15,
        max_retries: int = 6,
        timeout_s: float = 60,
        session: requests.Session | None = None,
    ) -> None:
        self._session = session or requests.Session()
        self._session.headers["Authorization"] = f"OAuth {token}"
        self._session.headers["User-Agent"] = "parkwild/0.0.1 (wildlife side project; contact via Mapillary profile)"
        self._min_interval = min_interval_s
        self._max_retries = max_retries
        self._timeout = timeout_s
        self._last_call = 0.0
        self._lock = threading.Lock()  # the downloader calls get_image() from threads

    # ---- transport -----------------------------------------------------------

    def _throttle(self) -> None:
        """Sleep so consecutive requests are at least `min_interval` apart."""
        with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _get(self, path: str, params: dict) -> dict:
        """GET with throttling and exponential backoff. 4xx other than 429 are
        treated as my mistake and raised immediately with the server's message."""
        url = f"{GRAPH_URL}{path}"
        for attempt in range(self._max_retries + 1):
            self._throttle()
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                # Network blip: same treatment as a 5xx.
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
        raise MapillaryError(f"gave up on {path} after {self._max_retries} retries")

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(60.0, 2.0**attempt) + random.uniform(0, 1))

    # ---- endpoints -----------------------------------------------------------

    def search_images(
        self,
        bbox: BBox,
        *,
        fields: Sequence[str] = IMAGE_FIELDS,
        limit: int = SEARCH_LIMIT,
        **filters: str,
    ) -> list[dict]:
        """One /images search inside `bbox`. Extra keyword args become query
        filters (e.g. is_pano="false", start_captured_at="2020-01-01T00:00:00Z")."""
        if not bbox.fits_mapillary():
            raise ValueError(f"bbox area {bbox.area_deg2:.4f} deg^2 is over Mapillary's 0.01 limit; tile it first")
        params = {"bbox": bbox.as_mapillary(), "fields": ",".join(fields), "limit": limit, **filters}
        data = self._get("/images", params)
        return data.get("data", [])

    def get_image(self, image_id: str, *, fields: Sequence[str] = IMAGE_FIELDS) -> dict:
        """Entity lookup for one image. Used to refresh expired thumbnail URLs."""
        return self._get(f"/{image_id}", {"fields": ",".join(fields)})

    # ---- crawl ---------------------------------------------------------------

    def crawl(
        self,
        bbox: BBox,
        *,
        fields: Sequence[str] = IMAGE_FIELDS,
        tile_deg: float = DEFAULT_TILE_DEG,
        skip_tile_ids: frozenset[str] | set[str] = frozenset(),
        **filters: str,
    ) -> Iterator[TileResult]:
        """Enumerate every image in `bbox` by walking a grid of tiles.

        A tile that returns exactly SEARCH_LIMIT rows might be hiding more, so it is
        quartered and its children pushed onto the work stack. `skip_tile_ids` lets
        the caller pass tiles it already finished (from the `tiles` table) so an
        interrupted crawl resumes instead of restarting.
        """
        stack: list[BBox] = list(reversed(tile_bbox(bbox, tile_deg)))
        while stack:
            tile = stack.pop()
            if tile.tile_id in skip_tile_ids:
                continue
            records = self.search_images(tile, fields=fields, **filters)
            hit_cap = len(records) >= SEARCH_LIMIT
            can_split = tile.width_deg > MIN_SPLIT_TILE_DEG and tile.height_deg > MIN_SPLIT_TILE_DEG
            if hit_cap and can_split:
                log.info("tile %s hit the %d cap; splitting", tile.tile_id, SEARCH_LIMIT)
                stack.extend(reversed(tile.split()))
                yield TileResult(tile, records, hit_cap=True, split=True)
            else:
                if hit_cap:
                    log.warning("tile %s hit the cap at minimum size; coverage there is truncated", tile.tile_id)
                yield TileResult(tile, records, hit_cap=hit_cap, split=False)


# ---- record shaping ----------------------------------------------------------

def image_page_url(image_id: str) -> str:
    """Human-facing Mapillary page for an image. This is the link attribution
    needs to point at."""
    return f"https://www.mapillary.com/app/?pKey={image_id}"


def _point(geojson: dict | None) -> tuple[float | None, float | None]:
    if not geojson or geojson.get("type") != "Point":
        return None, None
    coords = geojson.get("coordinates") or []
    if len(coords) < 2:
        return None, None
    return float(coords[0]), float(coords[1])


def flatten_image(rec: dict, corridor: str | None = None) -> dict:
    """Turn one raw API record into a flat row for the `images` table.

    Position: I prefer `computed_geometry` (SfM-corrected) and fall back to the
    raw GPS `geometry`. Both are kept so I can measure how far they disagree.
    The raw record is stored as JSON too, so nothing the API gave me is lost if I
    change my mind about the columns later.
    """
    c_lon, c_lat = _point(rec.get("computed_geometry"))
    r_lon, r_lat = _point(rec.get("geometry"))
    if c_lon is not None:
        lon, lat, position_source = c_lon, c_lat, "computed"
    else:
        lon, lat, position_source = r_lon, r_lat, "gps"

    captured_ms = rec.get("captured_at")
    captured_at = (
        datetime.fromtimestamp(captured_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
        if captured_ms is not None
        else None
    )
    creator = rec.get("creator") or {}
    detections = rec.get("detections")
    if isinstance(detections, dict):  # entity responses wrap the list in {"data": [...]}
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
