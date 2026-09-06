"""The Overpass call is exercised by the real run; the shaping is tested here."""
from parkwild.amenities import TRAIL_MIN_M, items_from_elements, trails_from_roads


def _el(i, tags, lon=-110.5, lat=44.6):
    return {"type": "node", "id": i, "lat": lat, "lon": lon, "tags": tags}


def test_items_keep_kinds_names_and_boundary_rules():
    square = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-111, 44], [-110, 44], [-110, 45], [-111, 45], [-111, 44]]]}}
    els = [
        _el(1, {"tourism": "camp_site", "name": "Madison", "fee": "yes", "capacity": "278"}),
        _el(2, {"tourism": "camp_site"}, lon=-109.5),                       # outside, unnamed: camping is kept anywhere
        _el(3, {"tourism": "viewpoint"}, lon=-109.5),                       # outside: facilities are dropped
        _el(4, {"tourism": "viewpoint"}),                                   # unnamed viewpoint inside: kept with a default name
        _el(5, {"natural": "geyser"}),                                      # feature without a name: dropped
        _el(6, {"natural": "geyser", "name": "Castle Geyser", "ele": "2230"}),
        _el(7, {"tourism": "information", "information": "board", "name": "Sign"}),      # not a visitor centre
        _el(8, {"tourism": "information", "information": "visitor_centre", "name": "Albright Visitor Center"}),
        _el(9, {"highway": "trailhead", "name": "Fairy Falls Trailhead"}),
    ]
    items, counts = items_from_elements(els, square)
    kinds = {it["name"]: it["kind"] for it in items}
    assert kinds == {"Madison": "camp", "Campsite": "camp", "Viewpoint": "viewpoint", "Castle Geyser": "feature",
                     "Albright Visitor Center": "info", "Fairy Falls Trailhead": "trailhead"}
    assert counts == {"fetched": 9, "no_name": 1, "outside": 1, "other_info": 1}
    madison = next(it for it in items if it["name"] == "Madison")
    assert madison["tags"] == {"fee": "yes", "capacity": "278"} and madison["named"]


def test_trails_sum_named_trail_edges_only():
    roads = {"names": ["Grand Loop Road", "Fairy Falls Trail"], "edges": [
        [0, 1, 400, 0, 0, 0, [[-110.8, 44.5], [-110.79, 44.5]]],          # a road
        [1, 2, 300, 1, 0, 1, [[-110.8, 44.5], [-110.79, 44.51]]],         # trail piece
        [2, 3, 450, 1, 0, 1, [[-110.79, 44.51], [-110.78, 44.52], [-110.77, 44.53]]],
        [3, 4, 200, 1, 0, -1, [[-110.77, 44.53], [-110.76, 44.53]]],      # unnamed trail
    ]}
    trails = trails_from_roads(roads)
    assert [t["name"] for t in trails] == ["Fairy Falls Trail"] and trails[0]["length_m"] == 750 >= TRAIL_MIN_M
    assert trails[0]["pieces"] == 2 and trails[0]["lon"] == -110.78       # midpoint of the longest piece
