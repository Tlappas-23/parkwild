import math

import pytest

from parkwild.geo import (
    MAPILLARY_MAX_BBOX_AREA_DEG2,
    BBox,
    haversine_m,
    path_length_m,
    tile_bbox,
)


def test_bbox_validation():
    with pytest.raises(ValueError):
        BBox(-110.1, 44.9, -110.4, 44.8)  # inverted
    with pytest.raises(ValueError):
        BBox(44.85, -110.42, 44.96, -110.10)  # lat/lon swapped: lon 44 < lon 44.96 ok, but lat -110 is out of range


def test_bbox_string_orders():
    b = BBox(-110.42, 44.85, -110.10, 44.96)
    assert b.as_mapillary() == "-110.42,44.85,-110.1,44.96"      # left,bottom,right,top
    assert b.as_overpass() == "44.85,-110.42,44.96,-110.1"       # south,west,north,east


def test_tiles_cover_bbox_exactly_and_fit_mapillary():
    b = BBox(-110.42, 44.85, -110.10, 44.96)   # 0.32 x 0.11 deg = 0.0352 deg^2: too big for one query
    assert not b.fits_mapillary()
    tiles = tile_bbox(b, 0.05)
    assert len(tiles) == 7 * 3
    assert all(t.fits_mapillary() for t in tiles)
    assert all(b.min_lon <= t.min_lon < t.max_lon <= b.max_lon for t in tiles)
    assert all(b.min_lat <= t.min_lat < t.max_lat <= b.max_lat for t in tiles)
    assert math.isclose(sum(t.area_deg2 for t in tiles), b.area_deg2, rel_tol=1e-9)
    assert len({t.tile_id for t in tiles}) == len(tiles)


def test_tiles_exact_multiple_has_no_sliver():
    tiles = tile_bbox(BBox(0.0, 0.0, 0.1, 0.1), 0.05)
    assert len(tiles) == 4


def test_tile_deg_too_large_rejected():
    with pytest.raises(ValueError):
        tile_bbox(BBox(0, 0, 1, 1), math.sqrt(MAPILLARY_MAX_BBOX_AREA_DEG2))


def test_split_quarters():
    b = BBox(0.0, 0.0, 0.1, 0.1)
    kids = b.split()
    assert len(kids) == 4
    assert math.isclose(sum(k.area_deg2 for k in kids), b.area_deg2)
    assert all(k.width_deg == 0.05 and k.height_deg == 0.05 for k in kids)


def test_haversine_one_degree_latitude():
    # 2*pi*R/360 with R = 6371008.8 m
    assert math.isclose(haversine_m(0, 0, 0, 1), 111_194.9, rel_tol=1e-4)


def test_path_length_clipping():
    box = BBox(0.0, 0.0, 1.0, 1.0)
    inside = [(0.1, 0.5), (0.2, 0.5)]
    straddle = [(0.9, 0.5), (1.1, 0.5)]
    outside = [(1.1, 0.5), (1.2, 0.5)]
    full = path_length_m(inside)
    assert math.isclose(path_length_m(inside, clip_to=box), full)
    assert math.isclose(path_length_m(straddle, clip_to=box), path_length_m(straddle) / 2)
    assert path_length_m(outside, clip_to=box) == 0


def test_overpass_requests_identify_themselves():
    """overpass-api.de returns 406 to the default python-requests User-Agent."""
    from urllib.parse import urlparse

    from parkwild.overpass import HEADERS, OVERPASS_URLS
    assert "parkwild" in HEADERS["User-Agent"]
    assert urlparse(OVERPASS_URLS[0]).netloc == "lz4.overpass-api.de"


def test_point_in_geometry_polygon_and_multipolygon():
    from parkwild.geo import point_in_geometry
    square = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}
    assert point_in_geometry(1, 1, square) and not point_in_geometry(3, 1, square)
    multi = {"type": "MultiPolygon", "coordinates": [square["coordinates"], [[[10, 10], [12, 10], [12, 12], [10, 12], [10, 10]]]]}
    assert point_in_geometry(11, 11, multi) and not point_in_geometry(5, 5, multi)
