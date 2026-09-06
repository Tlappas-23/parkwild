"""Places are a pure roll-up of the park's exported files: no network unless asked."""
import json
from datetime import date

import duckdb

from parkwild.config import BBox, Park
from parkwild.places import build_places, collect_places, sample_lines, wikipedia_views


def _park():
    return Park(key="testpark", name="Test National Park", state="XX", inat_place_id=1, bbox=BBox(-1, -1, 1, 1))


def _export(tmp):
    d = tmp / "testpark"
    d.mkdir()
    (d / "landmarks.json").write_text(json.dumps({"park": "testpark", "landmarks": [
        {"id": "node/1", "name": "Big Peak", "kind": "peak", "lon": 0.0, "lat": 0.0, "ele_m": 2000, "url": "https://en.wikipedia.org/wiki/Big_Peak"}]}))
    (d / "amenities.json").write_text(json.dumps({"park": "testpark", "items": [
        {"id": "node/2", "kind": "viewpoint", "sub": "viewpoint", "name": "Sunset Point", "named": True, "lon": 0.02, "lat": 0.0, "tags": {"ele": "1500"}},
        {"id": "node/3", "kind": "camp", "sub": "camp site", "name": "Campsite", "named": False, "lon": 0.5, "lat": 0.5, "tags": {}},
        {"id": "node/1", "kind": "feature", "sub": "peak", "name": "Big Peak", "named": True, "lon": 0.0, "lat": 0.0, "tags": {}}],
        "trails": [{"id": "trail/1", "kind": "trail", "name": "Rim Trail", "length_m": 3000, "pieces": 1, "lon": 0.05, "lat": 0.1}]}))
    (d / "roads.json").write_text(json.dumps({"park": "testpark", "nodes": [[0.04, 0.1], [0.07, 0.1]], "names": ["Rim Trail"],
                                              "edges": [[0, 1, 3300, 1, 0, 0, [[0.04, 0.1], [0.07, 0.1]]]]}))
    con = duckdb.connect()
    con.execute("CREATE TABLE s (sighting_id VARCHAR, lon DOUBLE, lat DOUBLE, observed_on DATE, "
                "scientific_name VARCHAR, common_name VARCHAR, coordinate_status VARCHAR)")
    rows = [("a", 0.001, 0.001, "2024-06-10", "Cervus canadensis", "Elk", "open"),          # by the peak, June
            ("b", 0.002, -0.001, "2024-07-01", "Cervus canadensis", "Elk", "open"),         # by the peak, July
            ("c", 0.0, 0.0, "2024-07-15", "Ursus americanus", "Black Bear", "obscured"),    # obscured: never placed
            ("d", 0.055, 0.1015, "2023-05-02", "Corvus corax", "Raven", "open"),            # on the trail (170 m off)
            ("e", 0.3, 0.3, "2024-06-01", "Corvus corax", "Raven", "open")]                  # far from everything
    con.executemany("INSERT INTO s VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    con.execute(f"COPY s TO '{d / 'sightings.parquet'}' (FORMAT PARQUET)")
    con.close()
    return d


def test_places_roll_up_sightings_by_place_month_and_species(tmp_path, monkeypatch):
    d = _export(tmp_path)
    written = []
    monkeypatch.setattr("parkwild.places.write_park_manifest", lambda out_dir, key: written.append(key))   # the manifest needs a configured park
    stats = build_places(_park(), d, views=False)
    assert written == ["testpark"]
    j = json.loads((d / "places.json").read_text())
    assert stats["places"] == 3 and stats["items_unnamed"] == 1 and stats["duplicates"] == 1
    names = [p["name"] for p in j["places"]]
    assert names == ["Big Peak", "Rim Trail", "Sunset Point"]                 # most recorded first, then A to Z
    peak = j["places"][0]
    assert peak["src"] == "landmark" and peak["near"]["n"] == 2 and peak["near"]["months"][5] == 1 and peak["near"]["months"][6] == 1
    assert peak["near"]["top"] == [["Cervus canadensis", 2]] and "views_pm" not in peak
    trail = j["places"][1]
    assert trail["src"] == "trail" and trail["length_m"] == 3000 and trail["near"]["n"] == 1 and trail["near"]["top"][0][0] == "Corvus corax"
    assert j["places"][2]["near"]["n"] == 0 and j["places"][2]["ele_m"] == 1500.0


def test_trail_samples_follow_the_line():
    pts = sample_lines([[[0.0, 0.0], [0.01, 0.0]]], step_m=300)         # ~1113 m east
    assert len(pts) == 4 and pts[0] == (0.0, 0.0) and abs(pts[-1][0] - 0.0081) < 0.0005


def test_collect_places_without_files():
    places, counts = collect_places(None, None, None)
    assert places == [] and counts["landmarks"] == 0


def test_pageviews_average_and_failure(monkeypatch):
    class R:
        def __init__(self, code, items): self.status_code, self._items = code, items
        def json(self): return {"items": self._items}
    class S:
        def __init__(self, resp): self.resp, self.url = resp, None
        def get(self, url, **kw):
            self.url = url
            return self.resp
    s = S(R(200, [{"views": 100}, {"views": 300}]))
    assert wikipedia_views("https://en.wikipedia.org/wiki/Angels_Landing", session=s, today=date(2026, 9, 6)) == 200
    assert "Angels_Landing/monthly/20250901/20260831" in s.url
    assert wikipedia_views("https://en.wikipedia.org/wiki/X", session=S(R(404, []))) is None
    assert wikipedia_views("https://example.org/no-wiki", session=s) is None
