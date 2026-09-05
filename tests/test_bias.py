from conftest import image_row, inat_observations

from parkwild import inaturalist
from parkwild.bias import image_coverage_cells, render_bias_markdown, road_bias, seasonal_bias
from parkwild.geo import BBox


def test_road_bias_counts_sightings_near_images_as_covered(store):
    # Two camera positions in the corridor; the bison sighting is 40 m from one, the raven 9 km away.
    store.upsert_images([image_row("a", lon=-110.2, lat=44.9), image_row("b", lon=-110.25, lat=44.92)])
    obs = inat_observations()
    rows = [inaturalist.normalize(o, "yellowstone") for o in obs]
    rows[2]["lon"], rows[2]["lat"] = -110.10, 44.95          # move the raven well away from any camera
    store.upsert_sightings(rows)
    bbox = BBox(-110.42, 44.85, -110.10, 44.96)
    r = road_bias(store, "yellowstone", "test", bbox)
    # grizzly is obscured -> excluded; bison covered; raven not covered
    assert r["n_sightings_in_bbox"] == 2 and r["n_covered"] == 1
    assert abs(r["fraction_outside_coverage"] - 0.5) < 1e-9
    assert r["by_class"]["Mammalia"]["fraction_outside"] == 0.0 and r["by_class"]["Aves"]["fraction_outside"] == 1.0
    assert len(image_coverage_cells(store, "test", ring=0)) == 2


def test_seasonal_bias_histograms(store):
    store.upsert_images([image_row("a", captured_at_ms=1_689_000_000_000), image_row("b", captured_at_ms=1_689_100_000_000)])  # 10-11 July 2023
    store.upsert_sightings([inaturalist.normalize(o, "yellowstone") for o in inat_observations()])                           # all June 2023
    s = seasonal_bias(store, "yellowstone", "test")
    assert s["images_by_month"][6] == 2 and s["sightings_by_month"][5] == 3
    assert s["images_summer_share"] == 1.0 and s["sightings_summer_share"] == 1.0
    assert 7 not in s["months_with_no_imagery"] and 1 in s["months_with_no_imagery"]
    md = render_bias_markdown(road_bias(store, "yellowstone", "test", BBox(-111, 44, -109, 46)), s)
    assert "Road bias" in md and "| imagery |" in md
