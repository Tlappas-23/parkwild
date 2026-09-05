import json

from conftest import inat_observations

from parkwild import inaturalist
from parkwild.photos import DISPLAYABLE, export_photos, parse_photo


def _obs_with_photos():
    base = inat_observations()
    bison = {**base[0], "faves_count": 3, "photos": [
        {"id": 111, "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/111/square.jpeg", "license_code": "cc-by-nc"},
        {"id": 112, "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/112/square.jpg", "license_code": "cc-by"},
    ]}
    grizzly = {**base[1], "faves_count": 9, "photos": [{"id": 222, "url": "https://static.inaturalist.org/photos/222/square.jpg", "license_code": "cc0"}]}
    raven = {**base[2], "faves_count": 0, "photos": [
        {"id": 333, "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/333/square.jpeg", "license_code": None},          # all rights reserved
        {"id": 334, "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/334/square.jpeg", "license_code": "cc-by-nd"},     # no derivatives
    ]}
    return [bison, grizzly, raven]


def test_parse_photo_hosts():
    assert parse_photo({"url": "https://inaturalist-open-data.s3.amazonaws.com/photos/437492430/square.jpeg"}) == (437492430, "jpeg", 0)
    assert parse_photo({"url": "https://static.inaturalist.org/photos/5/square.jpg"}) == (5, "jpg", 1)
    assert parse_photo({"url": "https://elsewhere.example/photos/5/square.jpg"}) is None
    assert "cc-by-nd" not in DISPLAYABLE and "cc-by-nc" in DISPLAYABLE


def test_export_photos_respects_licences_and_sensitivity(store, tmp_path):
    store.upsert_sightings([inaturalist.normalize(o, "yellowstone") for o in _obs_with_photos()])
    r = export_photos(store, "yellowstone", tmp_path, rules=[])
    sp = json.loads((tmp_path / "photos_species.json").read_text())["species"]
    cells = json.loads((tmp_path / "photos_cells.json").read_text())
    # raven: both photos undisplayable -> no gallery, no cell
    assert "Corvus corax" not in sp
    # bison: one photo per observation, the first displayable one
    assert [p["i"] for p in sp["Bison bison"]] == [111] and sp["Bison bison"][0]["l"] == "CC BY-NC" and sp["Bison bison"][0]["o"] == "alice"
    # grizzly: obscured coordinates -> gallery yes, cell no
    assert sp["Ursus arctos"][0]["i"] == 222 and sp["Ursus arctos"][0]["c"] is None
    cell_species = {cells["species_index"][e[0]] for entries in cells["cells"].values() for e in entries}
    assert cell_species == {"Bison bison"}
    assert r["displayable"] == 3 and r["photos"] == 5
