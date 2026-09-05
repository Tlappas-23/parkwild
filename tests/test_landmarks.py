"""Tour matching is the only offline part of parkwild.landmarks; the fetchers
talk to iNaturalist, Overpass and Wikipedia and are exercised by the real run."""
from parkwild.config import Park
from parkwild.geo import BBox
from parkwild.landmarks import KINDS, MAX_PER_KIND, _kind, cap_by_kind, match_tour


def _lm(id_, name, kind="geyser", rank=0):
    return {"id": id_, "name": name, "kind": kind, "rank": rank, "lon": -110.8, "lat": 44.46, "ele_m": None, "wikidata": "Q1", "url": None}


def test_match_tour_exact_then_prefix_then_fallback_then_missing():
    park = Park(key="t", name="T", state="WY", inat_place_id=1, bbox=BBox.from_list([-111, 44, -109, 45]),
                tour=("Old Faithful", "Lower Falls", "Hayden Valley", "Nowhere"), tour_fallback={"Hayden Valley": (-110.44, 44.66)})
    landmarks = [_lm("node/1", "Old Faithful"), _lm("way/2", "Lower Falls of the Yellowstone River", "waterfall", 2),
                 _lm("node/3", "Old Faithful Inn", "historic", 12)]
    stops, missing = match_tour(park, landmarks)
    assert [s["name"] for s in stops] == ["Old Faithful", "Lower Falls of the Yellowstone River", "Hayden Valley"]
    assert [s["tour"] for s in stops] == [0, 1, 2] and stops[2]["id"] == "config/2" and missing == ["Nowhere"]
    # a configured coordinate wins over a fuzzy match (the Norris museum problem)
    park2 = Park(key="t", name="T", state="WY", inat_place_id=1, bbox=BBox.from_list([-111, 44, -109, 45]),
                 tour=("Old Faithful",), tour_fallback={"Old Faithful": (-110.83, 44.46)})
    stops2, _ = match_tour(park2, [_lm("node/3", "Old Faithful Inn", "historic", 12)])
    assert stops2[0]["id"] == "config/0"
    assert any(lm["id"] == "config/2" for lm in landmarks)      # the fallback joins the landmark list so the map can draw it


def test_kind_ranks_follow_the_table():
    assert _kind({"natural": "geyser"}) == (0, "geyser")
    assert _kind({"tourism": "information", "information": "visitor_centre"})[1] == "visitor centre"
    assert _kind({"natural": "tree"}) is None and len(KINDS) > 5


def test_cap_keeps_tour_stops_past_the_kind_limit():
    geysers = [_lm(f"node/{i}", f"Geyser {i:03d}") for i in range(MAX_PER_KIND + 5)]
    stops = [geysers[-1]]          # the alphabetically last one is on the tour
    kept, dropped = cap_by_kind(geysers, stops)
    assert len(kept) == MAX_PER_KIND + 1 and geysers[-1] in kept and dropped == 4
