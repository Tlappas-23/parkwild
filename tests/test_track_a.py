import json
from datetime import datetime

from conftest import gbif_occurrences, inat_observations

from parkwild import gbif, inaturalist
from parkwild.config import Suppression, load_suppression
from parkwild.export import cells_geojson, export_park, species_json, suppression_for
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
    # open-coordinate canonical rows: bison 1001, raven 1003, raven 5004 (obscured grizzly & wolf excluded).
    # bison and raven 1003 are 40 m apart, i.e. the same r9 cell => 2 cells.
    assert r["cells"]["sightings_in_cells"] == 3 and r["cells"]["cells"] == 2 and len(fc["features"]) == 2
    names = [e["n"] for e in fc["species_index"]]
    assert set(names) == {"Bison bison", "Corvus corax"} and fc["h3_res"] == 9
    shared = next(f for f in fc["features"] if f["properties"]["count"] == 2)
    entries = {names[e[0]]: e for e in shared["properties"]["sp"]}
    assert entries["Bison bison"][1] == 1 and entries["Bison bison"][2] == 1 and entries["Bison bison"][4] == 2023
    ring = shared["geometry"]["coordinates"][0]
    assert len(ring) == 7 and -180 <= ring[0][0] <= 180 and -90 <= ring[0][1] <= 90   # lon, lat order
    assert all(len(str(v).split(".")[-1]) <= 5 for pt in ring for v in pt)            # 5-decimal coordinates
    sp = json.loads((out / "species.json").read_text())
    by_name = {s["scientific_name"]: s for s in sp["species"]}
    assert by_name["Canis lupus"]["obscured_coordinates"] == 1 and by_name["Canis lupus"]["open_coordinates"] == 0
    assert by_name["Corvus corax"]["sightings"] == 2 and by_name["Corvus corax"]["months"][5] == 1 and by_name["Corvus corax"]["months"][6] == 1
    assert sp["notes"]["recall"] == "unmeasured"
    assert r["sightings"]["rows"] == 5
    manifest = json.loads((out / "manifest.json").read_text())
    assert set(manifest["files"]) == {"cells.geojson", "species.json", "sightings.parquet", "photos_species.json", "photos_cells.json"}
    assert all(len(v["sha256"]) == 64 for v in manifest["files"].values())


def test_cells_exclude_obscured_even_if_only_rows(store, tmp_path):
    store.upsert_sightings([inaturalist.normalize(inat_observations()[1], "yellowstone")])   # grizzly, obscured
    r = cells_geojson(store, "yellowstone", tmp_path / "c.geojson")
    assert r["features"] == 0
    species_json(store, "yellowstone", tmp_path / "s.json")
    assert json.loads((tmp_path / "s.json").read_text())["species"][0]["obscured_coordinates"] == 1


def test_suppression_list_loads_with_reasons():
    rules = load_suppression()
    names = {r.name for r in rules}
    assert "Canis lupus" in names and "Gulo gulo" in names
    assert all(r.why for r in rules)
    wolf = suppression_for("Canis lupus occidentalis", rules, set())
    assert wolf is not None and wolf.action == "exclude"
    assert suppression_for("Bison bison", rules, set()) is None
    auto = suppression_for("Ursus arctos horribilis", [], {"Ursus arctos horribilis"})
    assert auto is not None and auto.action == "coarsen" and auto.res == 6


def test_export_applies_suppression(store, tmp_path):
    _load(store)
    dedupe(store, "yellowstone")
    # Make the wolf row open-coordinate so only the suppression list can keep it off the map.
    store.con.execute("UPDATE sightings SET coordinate_status = 'open' WHERE sighting_id = 'gbif:5003'")
    rules = [Suppression("Canis lupus", "gray wolf", "exclude", None, "test"),
             Suppression("Corvus corax", "raven", "coarsen", 6, "test")]
    r = cells_geojson(store, "yellowstone", tmp_path / "c.geojson", rules=rules)
    fc = json.loads((tmp_path / "c.geojson").read_text())
    names = [e["n"] for e in fc["species_index"]]
    assert "Canis lupus" not in names and r["excluded"] == 1
    raven_idx = names.index("Corvus corax")
    raven_cells = [f for f in fc["features"] if any(e[0] == raven_idx for e in f["properties"]["sp"])]
    assert raven_cells and all(f["properties"]["coarsened"] and f["properties"]["res"] == 6 for f in raven_cells)
    assert fc["suppressed"]["excluded"] == {"Canis lupus": 1}
    species_json(store, "yellowstone", tmp_path / "s.json", rules=rules)
    sp = {s["scientific_name"]: s for s in json.loads((tmp_path / "s.json").read_text())["species"]}
    assert sp["Canis lupus"]["suppression"]["action"] == "exclude" and sp["Bison bison"]["suppression"] is None


def test_canonical_species_collapses_subspecies_and_synonyms():
    from parkwild.config import canonical_species, load_synonyms
    syn = load_synonyms()
    assert canonical_species("Bos bison bison", syn) == "Bison bison"
    assert canonical_species("Bos bison", syn) == "Bison bison"
    assert canonical_species("Cervus canadensis canadensis", syn) == "Cervus canadensis"
    assert canonical_species("Cervus elaphus", syn) == "Cervus canadensis"
    assert canonical_species("Ursus arctos horribilis", syn) == "Ursus arctos"
    assert canonical_species("Corvus corax", syn) == "Corvus corax"
    assert canonical_species(None, syn) is None


def test_species_json_merges_names(store, tmp_path):
    _load(store)
    # A GBIF-spelled bison and a subspecies row should fold into the iNaturalist species.
    from parkwild.gbif import normalize as gn
    extra = gn({**gbif_occurrences()[0], "key": 9001, "species": "Bos bison", "datasetKey": "d1"}, "yellowstone")
    extra2 = gn({**gbif_occurrences()[0], "key": 9002, "species": "Bos bison bison", "taxonRank": "SUBSPECIES", "datasetKey": "d1"}, "yellowstone")
    store.upsert_sightings([extra, extra2])
    species_json(store, "yellowstone", tmp_path / "s.json")
    sp = {s["scientific_name"]: s for s in json.loads((tmp_path / "s.json").read_text())["species"]}
    assert "Bos bison" not in sp and sp["Bison bison"]["sightings"] == 4
    assert set(sp["Bison bison"]["aliases"]) == {"Bos bison", "Bos bison bison"}


def test_auto_sensitive_requires_a_majority(store):
    """E-019: one flagged observation among many must not coarsen a species."""
    from parkwild.export import auto_sensitive_species
    base = inat_observations()[0]
    rows = []
    for i in range(10):   # bison: one of ten flagged
        o = {**base, "id": 2000 + i, "taxon_geoprivacy": "obscured" if i == 0 else None}
        rows.append(inaturalist.normalize(o, "yellowstone"))
    for i in range(4):    # otter: all flagged
        o = {**base, "id": 3000 + i, "taxon_geoprivacy": "obscured",
             "taxon": {"id": 9, "name": "Lontra canadensis", "preferred_common_name": "River Otter", "rank": "species", "iconic_taxon_name": "Mammalia"}}
        rows.append(inaturalist.normalize(o, "yellowstone"))
    store.upsert_sightings(rows)
    assert auto_sensitive_species(store, "yellowstone") == {"Lontra canadensis"}


def test_common_name_is_the_inaturalist_majority_in_both_files(store, tmp_path):
    """E-024: cells.geojson took the first name seen and species.json a plain
    majority, so the map said "American Elk" while the list said "Wapiti".
    Both now use the iNaturalist majority, GBIF names only when iNaturalist
    has none, and the losing names stay searchable."""
    _load(store)
    obs = inat_observations()[0]
    rows = []
    for i, cn in enumerate(["American Elk", "Wapiti", "Wapiti", "Wapiti"]):
        o = {**obs, "id": 7000 + i, "taxon": {**obs["taxon"], "id": 7, "name": "Cervus canadensis", "preferred_common_name": cn}}
        rows.append(inaturalist.normalize(o, "yellowstone"))
    base = gbif_occurrences()[0]
    for i in range(5):    # a GBIF vernacular that would win on count alone
        occ = {**base, "key": 8000 + i, "species": "Cervus canadensis", "vernacularName": "Elk unknown", "datasetKey": "d1"}
        rows.append(gbif.normalize(occ, "yellowstone"))
    rows.append(gbif.normalize({**base, "key": 8100, "species": "Alces alces", "vernacularName": "Moose", "datasetKey": "d1"}, "yellowstone"))
    store.upsert_sightings(rows)
    cells_geojson(store, "yellowstone", tmp_path / "c.geojson", rules=[])
    species_json(store, "yellowstone", tmp_path / "s.json", rules=[])
    cell_names = {e["n"]: e["c"] for e in json.loads((tmp_path / "c.geojson").read_text())["species_index"]}
    sp = {s["scientific_name"]: s for s in json.loads((tmp_path / "s.json").read_text())["species"]}
    assert cell_names["Cervus canadensis"] == "Wapiti" and sp["Cervus canadensis"]["common_name"] == "Wapiti"
    assert sp["Cervus canadensis"]["other_names"] == ["American Elk", "Elk unknown"]
    assert cell_names["Alces alces"] == "Moose" and sp["Alces alces"]["common_name"] == "Moose"     # GBIF-only fallback
    assert all(cell_names[n] == sp[n]["common_name"] for n in cell_names)
