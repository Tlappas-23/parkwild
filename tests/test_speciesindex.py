"""The cross-park species index is a pure roll-up of the shipped files."""
import json

from parkwild.speciesindex import build_species_index, centroid, species_index_stamp


def _square(x, y, d=0.01):
    return [[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]


def _cell(ring, cell, sp):
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {"cell": cell, "res": 9, "sp": sp}}


def _park(tmp, key, species, cells, name=None):
    d = tmp / key
    d.mkdir()
    (d / "species.json").write_text(json.dumps({"park": key, "species": species}))
    (d / "cells.geojson").write_text(json.dumps(cells))
    if name:
        (d / "manifest.json").write_text(json.dumps({"park": key, "name": name, "state": "WY"}))


def _sp(name, common, sightings, **kw):
    base = {"scientific_name": name, "common_name": common, "class": "Mammalia", "aliases": [], "other_names": [], "suppression": None,
            "sightings": sightings, "confidence_basis": {"human_verified": sightings, "model_predicted": 0}}
    base.update(kw)
    return base


def test_index_rolls_parks_up_and_keeps_the_busiest_cells(tmp_path):
    elk = "Cervus canadensis"
    wolf = "Canis lupus"
    _park(tmp_path, "a",
          [_sp(elk, "Elk", 10, aliases=["Cervus elaphus"], other_names=["Wapiti"]),
           _sp(wolf, "Gray Wolf", 5, suppression={"action": "exclude", "res": None, "why": "sensitive"})],
          {"type": "FeatureCollection", "species_index": [{"n": elk, "c": "Elk", "k": "Mammalia"}, {"n": wolf, "c": "Gray Wolf", "k": "Mammalia"}],
           "features": [
               _cell(_square(-110.0, 44.0), "c1", [[0, 3, 3, 0, 2020, 2021]]),
               _cell(_square(-110.5, 44.5), "c2", [[0, 7, 7, 0, 2019, 2026]]),
           ]}, name="Park A")
    _park(tmp_path, "b",
          [_sp(elk, None, 4)],
          {"type": "FeatureCollection", "species_index": [{"n": elk, "c": None, "k": "Mammalia"}],
           "features": [_cell(_square(-113.0, 37.0), "c3", [[0, 4, 4, 0, 2022, 2022]])]})
    out = tmp_path / "species_index.json"
    stats = build_species_index(tmp_path, out, top_cells=1)
    j = json.loads(out.read_text())
    assert stats["species"] == 2 and stats["parks"] == 2 and stats["non_species_cell_entries"] == 0
    assert j["parks"]["a"] == {"name": "Park A", "state": "WY"} and j["parks"]["b"]["name"] == "b"
    e, w = j["species"]                       # elk first: 14 sightings over both parks beats 5
    assert e["n"] == elk and e["c"] == "Elk" and e["total"] == 14 and sorted(e["other"]) == ["Cervus elaphus", "Wapiti"]
    assert e["parks"]["a"]["s"] == 10 and e["parks"]["a"]["cells"] == 2
    assert e["parks"]["a"]["top"] == [[-110.495, 44.505, 7, "c2", 9]]     # the busiest cell, one kept, centre of the square
    assert e["parks"]["b"]["cells"] == 1 and e["parks"]["b"]["top"][0][3] == "c3"
    assert w["parks"]["a"]["x"] == "exclude" and w["parks"]["a"]["cells"] == 0 and w["parks"]["a"]["top"] == []
    stamp = species_index_stamp(out)
    assert stamp and len(stamp["sha256"]) == 64 and stamp["bytes"] == out.stat().st_size
    assert species_index_stamp(tmp_path / "missing.json") is None


def test_centroid_drops_the_closing_vertex():
    lon, lat = centroid(_square(0.0, 0.0, 2.0))
    assert (round(lon, 6), round(lat, 6)) == (1.0, 1.0)
