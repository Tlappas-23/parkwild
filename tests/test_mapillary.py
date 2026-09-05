from datetime import datetime

from parkwild.geo import BBox
from parkwild.mapillary import (
    CAP_SUSPECT_ROWS,
    COVERAGE_FIELDS,
    SEARCH_LIMIT,
    MapillaryClient,
    MapillaryServerError,
    flatten_image,
    image_page_url,
    is_capped,
    is_capped_v1,
)

RAW = {
    "id": "123456789",
    "geometry": {"type": "Point", "coordinates": [-110.2001, 44.9001]},
    "computed_geometry": {"type": "Point", "coordinates": [-110.2, 44.9]},
    "captured_at": 1_700_000_000_000,
    "compass_angle": 91.5,
    "computed_compass_angle": 90.0,
    "camera_type": "perspective",
    "is_pano": False,
    "make": "GoPro", "model": "HERO9",
    "width": 4000, "height": 3000,
    "sequence": "seq-xyz",
    "creator": {"id": "42", "username": "alice"},
    "thumb_1024_url": "https://x/1024", "thumb_2048_url": "https://x/2048", "thumb_original_url": "https://x/orig",
}


def test_flatten_prefers_computed_geometry_and_keeps_attribution():
    row = flatten_image(RAW, "lamar_valley")
    assert row["image_id"] == "123456789"
    assert (row["lon"], row["lat"]) == (-110.2, 44.9)
    assert (row["lon_raw"], row["lat_raw"]) == (-110.2001, 44.9001)
    assert row["position_source"] == "computed"
    assert row["captured_at"] == datetime(2023, 11, 14, 22, 13, 20)
    assert row["creator_username"] == "alice" and row["creator_id"] == "42"
    assert row["license"] == "CC BY-SA 4.0"
    assert row["source_url"] == image_page_url("123456789")
    assert row["sequence_id"] == "seq-xyz"


def test_flatten_falls_back_to_gps():
    raw = {k: v for k, v in RAW.items() if k != "computed_geometry"}
    row = flatten_image(raw)
    assert row["position_source"] == "gps"
    assert (row["lon"], row["lat"]) == (-110.2001, 44.9001)
    assert row["corridor"] is None


def test_flatten_handles_missing_optional_fields():
    row = flatten_image({"id": "1"})
    assert row["lon"] is None and row["captured_at"] is None and row["creator_username"] is None
    assert row["license"] == "CC BY-SA 4.0"


class FakeClient(MapillaryClient):
    """Pretends busy tiles: anything wider than 0.02 deg returns a truncated-looking
    count just under 2000, the way the real server does."""

    def __init__(self):
        super().__init__("token", min_interval_s=0)
        self.calls = []

    def search_images(self, bbox, *, fields=COVERAGE_FIELDS, limit=SEARCH_LIMIT, retries=None, **filters):
        self.calls.append(bbox.tile_id)
        n = 1879 if bbox.width_deg > 0.02 else 7
        return [{"id": f"{bbox.tile_id}-{i}"} for i in range(n)]


def test_cap_zone_is_below_the_documented_limit():
    assert 1500 <= CAP_SUSPECT_ROWS < 1879 < SEARCH_LIMIT


def test_crawl_splits_capped_tiles_and_skips_done_ones():
    client = FakeClient()
    results = list(client.crawl(BBox(0, 0, 0.05, 0.05), tile_deg=0.05))
    statuses = [r.status for r in results]
    # 0.05 -> split -> 4 x 0.025 -> each split -> 16 x 0.0125 done
    assert statuses.count("split") == 5
    assert statuses.count("done") == 16
    assert all(len(r.records) == 7 for r in results if r.status == "done")

    done_ids = {r.tile.tile_id for r in results}
    client2 = FakeClient()
    assert list(client2.crawl(BBox(0, 0, 0.05, 0.05), tile_deg=0.05, skip_tile_ids=done_ids)) == []
    assert client2.calls == []


class HeavyTileClient(MapillaryClient):
    """Mimics what Mapillary did on Cades Cove: HTTP 500 for a 0.05 deg tile
    with too many images, fine answers for its quarters. Tiles at the minimum
    size still error, to exercise the give-up path."""

    def __init__(self):
        super().__init__("token", min_interval_s=0)
        self.calls = 0

    def search_images(self, bbox, *, fields=COVERAGE_FIELDS, limit=SEARCH_LIMIT, retries=None, **filters):
        self.calls += 1
        if bbox.width_deg > 0.03 or bbox.width_deg <= 0.0016:
            raise MapillaryServerError("500")
        return [{"id": f"{bbox.tile_id}-{i}"} for i in range(3)]


def test_crawl_splits_on_server_error_and_reports_unsplittable_errors():
    client = HeavyTileClient()
    results = list(client.crawl(BBox(0, 0, 0.05, 0.05), tile_deg=0.05))
    by_status = {}
    for r in results:
        by_status.setdefault(r.status, []).append(r)
    assert len(by_status["split"]) == 1 and by_status["split"][0].error == "500"
    assert len(by_status["done"]) == 4
    assert "error" not in by_status          # 0.025 quarters answered; nothing reached the floor

    tiny = list(client.crawl(BBox(0, 0, 0.0015, 0.0015), tile_deg=0.0015))
    assert [r.status for r in tiny] == ["error"] and tiny[0].records == []


# Measured 2026-09-05 on Lamar Valley: (rows returned by a tile, rows in its four quarters).
MEASURED_TILES = [(1573, 1513), (1604, 1604), (1849, 1849), (1879, 2559), (1929, 2771), (1938, 2847), (1973, 3371), (2000, 3165)]


def test_v1_cap_rule_undercounts():
    """The comparison that justifies replacing is_capped_v1 (E-001 -> E-002).
    Fails if v1 ever catches the measured truncations, which would mean the
    measurements were wrong or the constant drifted."""
    truncated = [(n, q) for n, q in MEASURED_TILES if q > n + 50]
    assert len(truncated) == 5
    missed_by_v1 = [n for n, _ in truncated if not is_capped_v1(n)]
    assert len(missed_by_v1) == 4, "v1 must miss the four sub-2000 truncations that motivated v2"
    assert all(is_capped(n) for n, _ in truncated), "v2 catches every measured truncation"
    complete = [n for n, q in MEASURED_TILES if q <= n + 50]
    assert all(not is_capped(n) for n in complete if n < CAP_SUSPECT_ROWS)
