"""The graph builder is pure; Overpass is exercised by the real run."""
from parkwild.roads import KIND_ROAD, KIND_TRAIL, MAX_EDGE_M, build_graph, simplify


def _way(wid, nodes, coords, **tags):
    return {"type": "way", "id": wid, "tags": {"highway": "secondary", **tags}, "nodes": nodes,
            "geometry": [{"lon": x, "lat": y} for x, y in coords]}


def test_edges_break_at_junctions_and_keep_kinds():
    # A west-east road through node 2, a north-south trail crossing it there.
    road = _way(1, [1, 2, 3], [(-110.0, 44.0), (-109.999, 44.0), (-109.998, 44.0)])
    trail = _way(2, [4, 2, 5], [(-109.999, 44.001), (-109.999, 44.0), (-109.999, 43.999)], highway="path")
    private = _way(3, [6, 7], [(-110.0, 44.01), (-109.999, 44.01)], access="private")
    g = build_graph([road, trail, private])
    assert g["stats"] == {"ways": 2, "dropped_access": 1, "dropped_outside": 0, "dropped_kind": 0, "junctions": 1}
    assert len(g["nodes"]) == 5 and len(g["edges"]) == 4          # both ways cut at the shared node
    kinds = sorted(e[3] for e in g["edges"])
    assert kinds == [KIND_ROAD, KIND_ROAD, KIND_TRAIL, KIND_TRAIL]
    assert all(70 < e[2] < 120 for e in g["edges"])                   # ~80 m and ~110 m legs


def test_long_ways_are_split_and_oneway_kept():
    coords = [(-110.0 + 0.002 * i, 44.0) for i in range(8)]          # ~160 m apart, 1.1 km total
    g = build_graph([_way(1, list(range(1, 9)), coords, oneway="yes")])
    assert len(g["edges"]) >= 3 and all(e[2] <= MAX_EDGE_M + 200 for e in g["edges"])
    assert all(e[4] == 1 for e in g["edges"])


def test_simplify_drops_collinear_points_only():
    line = [(-110.0, 44.0), (-109.999, 44.0), (-109.998, 44.0), (-109.997, 44.0)]
    assert simplify(line, 5.0) == [line[0], line[-1]]
    bent = [(-110.0, 44.0), (-109.999, 44.0005), (-109.998, 44.0)]
    assert simplify(bent, 5.0) == bent


def test_outside_the_boundary_only_major_roads_survive():
    ring = [[-110.1, 43.9], [-109.9, 43.9], [-109.9, 44.1], [-110.1, 44.1], [-110.1, 43.9]]
    square = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}}
    inside = _way(1, [1, 2], [(-110.0, 44.0), (-109.99, 44.0)], highway="residential")
    town_street = _way(2, [3, 4], [(-110.5, 44.0), (-110.49, 44.0)], highway="residential")
    approach = _way(3, [5, 6], [(-110.5, 44.01), (-110.49, 44.01)], highway="primary")
    parking = _way(4, [7, 8], [(-110.0, 44.01), (-109.99, 44.01)], highway="service")
    g = build_graph([inside, town_street, approach, parking], square)
    assert g["stats"]["ways"] == 2 and g["stats"]["dropped_outside"] == 1 and g["stats"]["dropped_kind"] == 1
