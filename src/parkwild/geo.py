"""
Plain-math geometry helpers: bounding boxes, tiling, and distances.

Nothing in here touches the network, which is the point. The tiling rule that
Mapillary imposes on bbox searches is the one piece of this project that will
silently break everything if I get it wrong, so it lives in a file I can unit
test in milliseconds.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# Mean Earth radius (IUGG). Good to well under 1% for the distances I care about.
EARTH_RADIUS_M = 6_371_008.8

# Mapillary rejects /images bbox searches whose *area* is >= 0.01 deg^2. Verified
# against the API docs on 2026-09-05 (changelog: "January 16, 2026: Bounding-box
# constraint formalized"). I tile at 0.05 x 0.05 deg = 0.0025 deg^2, a 4x margin.
# At 45 N a 0.05 deg tile is roughly 3.9 km east-west by 5.6 km north-south.
MAPILLARY_MAX_BBOX_AREA_DEG2 = 0.01
DEFAULT_TILE_DEG = 0.05


@dataclass(frozen=True)
class BBox:
    """A lon/lat rectangle. Field order matches Mapillary's `bbox` parameter
    (left, bottom, right, top) so I never have to think about which is which."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def __post_init__(self) -> None:
        # Fail loudly on inverted or out-of-range boxes. A swapped lon/lat pair is
        # the classic way to query the Indian Ocean instead of Wyoming.
        if not (-180 <= self.min_lon < self.max_lon <= 180):
            raise ValueError(f"bad longitude range: {self.min_lon}..{self.max_lon}")
        if not (-90 <= self.min_lat < self.max_lat <= 90):
            raise ValueError(f"bad latitude range: {self.min_lat}..{self.max_lat}")

    @classmethod
    def from_list(cls, values: Sequence[float]) -> BBox:
        if len(values) != 4:
            raise ValueError("bbox needs exactly 4 numbers: min_lon, min_lat, max_lon, max_lat")
        return cls(*(float(v) for v in values))

    @property
    def width_deg(self) -> float:
        return self.max_lon - self.min_lon

    @property
    def height_deg(self) -> float:
        return self.max_lat - self.min_lat

    @property
    def area_deg2(self) -> float:
        return self.width_deg * self.height_deg

    @property
    def center(self) -> tuple[float, float]:
        return ((self.min_lon + self.max_lon) / 2, (self.min_lat + self.max_lat) / 2)

    @property
    def tile_id(self) -> str:
        """Stable string key for progress tracking. Five decimals is about a metre,
        far finer than any tile I create, so equal tiles always get equal ids."""
        return f"{self.min_lon:.5f}_{self.min_lat:.5f}_{self.max_lon:.5f}_{self.max_lat:.5f}"

    def as_mapillary(self) -> str:
        """Mapillary wants `left,bottom,right,top`."""
        return f"{self.min_lon},{self.min_lat},{self.max_lon},{self.max_lat}"

    def as_overpass(self) -> str:
        """Overpass wants `south,west,north,east`, i.e. latitude first."""
        return f"{self.min_lat},{self.min_lon},{self.max_lat},{self.max_lon}"

    def contains(self, lon: float, lat: float) -> bool:
        return self.min_lon <= lon <= self.max_lon and self.min_lat <= lat <= self.max_lat

    def fits_mapillary(self) -> bool:
        return self.area_deg2 < MAPILLARY_MAX_BBOX_AREA_DEG2

    def split(self) -> list[BBox]:
        """Quarter the box. Used when a tile comes back at the 2000-image cap and
        I need finer tiles to see everything inside it."""
        mid_lon, mid_lat = self.center
        return [
            BBox(self.min_lon, self.min_lat, mid_lon, mid_lat),  # SW
            BBox(mid_lon, self.min_lat, self.max_lon, mid_lat),  # SE
            BBox(self.min_lon, mid_lat, mid_lon, self.max_lat),  # NW
            BBox(mid_lon, mid_lat, self.max_lon, self.max_lat),  # NE
        ]

    def approx_size_km(self) -> tuple[float, float]:
        """(east-west km, north-south km) measured through the box centre."""
        _, mid_lat = self.center
        ew = haversine_m(self.min_lon, mid_lat, self.max_lon, mid_lat) / 1000
        ns = haversine_m(self.min_lon, self.min_lat, self.min_lon, self.max_lat) / 1000
        return ew, ns


def tile_bbox(bbox: BBox, tile_deg: float = DEFAULT_TILE_DEG) -> list[BBox]:
    """Cut `bbox` into a grid of tiles no wider or taller than `tile_deg`.

    The last column and row are clipped to the bbox edge rather than overhanging
    it, so the tiles exactly cover the input and nothing outside it. Tiles come
    back row by row from the south-west corner, which keeps progress logs readable.
    """
    if tile_deg <= 0:
        raise ValueError("tile_deg must be positive")
    if tile_deg * tile_deg >= MAPILLARY_MAX_BBOX_AREA_DEG2:
        raise ValueError(
            f"tile_deg={tile_deg} gives tiles of {tile_deg * tile_deg:.4f} deg^2; "
            f"Mapillary rejects anything >= {MAPILLARY_MAX_BBOX_AREA_DEG2}"
        )
    # The tiny epsilon stops float noise turning an exact multiple into an extra
    # sliver-thin column.
    n_cols = math.ceil(bbox.width_deg / tile_deg - 1e-9)
    n_rows = math.ceil(bbox.height_deg / tile_deg - 1e-9)
    tiles: list[BBox] = []
    for row in range(n_rows):
        lat0 = bbox.min_lat + row * tile_deg
        lat1 = min(lat0 + tile_deg, bbox.max_lat)
        if lat1 - lat0 <= 1e-12:
            continue
        for col in range(n_cols):
            lon0 = bbox.min_lon + col * tile_deg
            lon1 = min(lon0 + tile_deg, bbox.max_lon)
            if lon1 - lon0 <= 1e-12:
                continue
            tiles.append(BBox(lon0, lat0, lon1, lat1))
    return tiles


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in metres between two lon/lat points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def path_length_m(coords: Iterable[tuple[float, float]], clip_to: BBox | None = None) -> float:
    """Length of a polyline given as (lon, lat) pairs.

    With `clip_to`, segments are only counted while inside the box: both ends in
    counts fully, one end in counts half, neither counts nothing. That is a crude
    clip, but it stops a 200 km highway that merely touches the corner of a corridor
    from swamping the road-length estimate.
    """
    total = 0.0
    prev: tuple[float, float] | None = None
    for lon, lat in coords:
        if prev is not None:
            seg = haversine_m(prev[0], prev[1], lon, lat)
            if clip_to is None:
                total += seg
            else:
                inside = clip_to.contains(*prev) + clip_to.contains(lon, lat)
                total += seg * inside / 2
        prev = (lon, lat)
    return total
