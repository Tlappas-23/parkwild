import json

from conftest import seed_phase0

from parkwild.trackb import EXCLUDED_LABELS, MIN_CONF, RANGE_M, detections_to_sightings


def test_detections_become_model_predicted_sightings(store, tmp_path):
    seed_phase0(store, tmp_path)
    # Fixture animal boxes: img1 0.88 bison (kept), img1 0.15 (below conf), img4 0.35/0.62 elk (0.62 kept), img5 0.55 elk (kept),
    # pano1 slice 0.41 (perspective run ignores it). img4 and img5 are 3 s apart in one sequence -> one chain.
    r = detections_to_sightings(store, "test", "yellowstone")
    assert r["boxes"] == 5 and r["kept_boxes"] == 3 and r["chains"] == 2 and r["written"] == 2
    rows = store.sql(
        "SELECT sighting_id, scientific_name, common_name, confidence_basis, positional_accuracy_m, raw_json "
        "FROM sightings WHERE source = 'mapillary_cv' ORDER BY sighting_id"
    )
    assert all(r[3] == "model_predicted" and r[4] == RANGE_M for r in rows)
    by_id = {r[0]: r for r in rows}
    bison = by_id["mapillary_cv:img1:full:0"]
    assert bison[1] == "Bison bison" and bison[2] == "american bison"           # classifier 0.91 >= 0.8: named
    elk = by_id["mapillary_cv:img4:full:1"]
    assert elk[1] == "Mammalia" and "unidentified" in elk[2]                    # classifier 0.71 < 0.8: not named
    assert json.loads(elk[5])["chain_frames"] == 2
    # idempotent, and stale derived rows do not survive a rerun
    store.upsert_sightings([{"sighting_id": "mapillary_cv:stale:full:9", "source": "mapillary_cv", "source_id": "stale", "park": "yellowstone",
                             "confidence_basis": "model_predicted", "coordinate_status": "missing", "raw_json": '{"corridor": "test"}'}])
    assert detections_to_sightings(store, "test", "yellowstone")["written"] == 2
    assert store.one("SELECT count(*) FROM sightings WHERE source = 'mapillary_cv'") == 2


def test_excluded_labels_and_threshold_are_documented():
    assert "human" in EXCLUDED_LABELS and "vehicle" in EXCLUDED_LABELS and MIN_CONF == 0.5
