import json
from datetime import datetime

from conftest import gbif_occurrences, inat_observations

from parkwild import gbif, inaturalist
from parkwild.export import cells_geojson, export_park, species_json
from parkwild.sightings import dedupe, park_summary


def test_inat_normalize_open_and_obscured():
    rows = [inaturalist.normalize(o, "yellowstone") for o in inat_observations()]
    bison, grizzly, raven = rows
    assert bison["sighting_id"] == "inaturalist:1001" and bison["coordinate_status"] == "open"
    assert bison["observed_at"] == datetime(2023, 6, 14, 15, 12)        # -06:00 -> UTC
    assert bison["license"] == "CC BY-NC 4.0" and "alice via iNaturalist" in bison["attribution"]
    assert grizzly["coordinate_status"] == "obscured" and grizzly["positional_accuracy_m"] == 28000
    assert grizzly["observed_at"] is None and grizzly["observed_on"] == "2023-06-15"
    assert raven["taxon_class"] == "Aves" and raven["license"] == "all rights reserved"
    assert all(r["confidence_basis"] == "human_verified" and r["source"] == "inaturalist" for r in rows)


def test_gbif_normalize_status_and_dates():
    rows = {o["key"]: gbif.normalize(o, "yellowstone") for o in gbif_occurrences()}
    assert rows[5001]["coordinate_status"] == "open" and rows[5001]["observed_at"] == datetime(2023, 6, 14, 15, 14)
    assert rows[5003]["coordinate_status"] == "obscured"                 # generalized + 15 km uncertainty
    assert rows[5004]["observed_on"] == "2021-07-04" and rows[5004]["observed_at"] is None   # date range
    assert rows[5004]["url"].startswith("https://www.gbif.org/occurrence/5004")
    assert rows[5001]["scientific_name"] == "Bison bison" and rows[5001]["taxon_rank"] == "species"


def _load(store):
    store.upsert_sightings([inaturalist.normalize(o, "yellowstone") for o in inat_observations()])
    store.upsert_sightings([gbif.normalize(o, "yellowstone") for o in gbif_occurrences()
                            if o["datasetKey"] != gbif.INAT_DATASET_KEY])


def test_dedupe_marks_cross_source_match_only(store):
    _load(store)
    r = dedupe(store, "yellowstone")
    # gbif:5001 is Alice's bison, 40 m and 2 minutes from inaturalist:1001 -> duplicate of it.
    assert r["marked_duplicate"] == 1
    assert store.one("SELECT duplicate_of FROM sightings WHERE sighting_id = 'gbif:5001'") == "inaturalist:1001"
    # the raven pair are different species+observer+day combos -> untouched
    assert store.one("SELECT duplicate_of FROM sightings WHERE sighting_id = 'gbif:5004'") is None
    s = park_summary(store, "yellowstone")
    assert s["total"] == 6 and s["canonical"] == 5


def test_exports(store, tmp_path):
    _load(store)
    dedupe(store, "yellowstone")
    out = tmp_path / "export"
    r = export_park(store, "yellowstone", out)
    fc = json.loads((out / "cells.geojson").read_text())
    # open-coordinate canonical rows: bison 1001, raven 1003, raven 5004 => 3 features (obscured grizzly & wolf excluded)
    assert r["cells"]["sightings_in_cells"] == 3 and len(fc["features"]) == 3
    props = {(f["properties"]["species"], f["properties"]["count"]) for f in fc["features"]}
    assert ("Bison bison", 1) in props and fc["h3_res"] == 9
    ring = fc["features"][0]["geometry"]["coordinates"][0]
    assert len(ring) == 7 and -180 <= ring[0][0] <= 180 and -90 <= ring[0][1] <= 90   # lon, lat order
    sp = json.loads((out / "species.json").read_text())
    by_name = {s["scientific_name"]: s for s in sp["species"]}
    assert by_name["Canis lupus"]["obscured_coordinates"] == 1 and by_name["Canis lupus"]["open_coordinates"] == 0
    assert by_name["Corvus corax"]["sightings"] == 2 and by_name["Corvus corax"]["months"][5] == 1 and by_name["Corvus corax"]["months"][6] == 1
    assert sp["notes"]["recall"] == "unmeasured"
    assert r["sightings"]["rows"] == 5
    manifest = json.loads((out / "manifest.json").read_text())
    assert set(manifest["files"]) == {"cells.geojson", "species.json", "sightings.parquet"}
    assert all(len(v["sha256"]) == 64 for v in manifest["files"].values())


def test_cells_exclude_obscured_even_if_only_rows(store, tmp_path):
    store.upsert_sightings([inaturalist.normalize(inat_observations()[1], "yellowstone")])   # grizzly, obscured
    r = cells_geojson(store, "yellowstone", tmp_path / "c.geojson")
    assert r["features"] == 0
    species_json(store, "yellowstone", tmp_path / "s.json")
    assert json.loads((tmp_path / "s.json").read_text())["species"][0]["obscured_coordinates"] == 1
