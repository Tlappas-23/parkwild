from conftest import image_row, seed_phase0


def test_upsert_images_dedupes_by_id(store):
    store.upsert_images([image_row("a"), image_row("b")])
    store.upsert_images([image_row("a", creator_username="bob")])
    assert store.count_images("test") == 2
    assert store.one("SELECT creator_username FROM images WHERE image_id = 'a'") == "bob"


def test_tile_progress_roundtrip(store):
    from parkwild.geo import BBox
    t = BBox(0, 0, 0.05, 0.05)
    assert store.done_tile_ids("test") == set()
    store.upsert_tile("test", t, "done", 12)
    assert store.done_tile_ids("test") == {t.tile_id}
    assert store.one("SELECT min_lat FROM tiles") == 0 and store.one("SELECT max_lon FROM tiles") == 0.05  # explicit columns
    store.upsert_tile("test", t, "error", 0)
    assert store.done_tile_ids("test") == set()          # error tiles get retried next run
    store.clear_tiles("test")
    assert store.count("tiles") == 0


def test_pending_download_spreads_across_sequences_and_selects_population(store):
    rows = [image_row(f"s1-{i}", sequence="s1") for i in range(10)]
    rows += [image_row(f"s2-{i}", sequence="s2") for i in range(10)]
    rows += [image_row("pano", sequence="s3", is_pano=True)]
    store.upsert_images(rows)
    store.record_download({"image_id": "s1-0", "local_path": "/x", "size_kind": "original", "error": None})
    store.record_download({"image_id": "s1-1", "local_path": None, "size_kind": None, "error": "HTTP 500"})

    picked = store.images_pending_download("test", limit=100, max_per_sequence=3)
    ids = {p["image_id"] for p in picked}
    assert "pano" not in ids
    assert "s1-0" not in ids            # already downloaded
    assert len([p for p in picked if p["sequence_id"] == "s1"]) == 3
    assert len([p for p in picked if p["sequence_id"] == "s2"]) == 3

    again = store.images_pending_download("test", limit=100, max_per_sequence=3)
    assert [p["image_id"] for p in again] == [p["image_id"] for p in picked]   # hash order => reproducible

    panos = store.images_pending_download("test", limit=100, max_per_sequence=3, population="pano")
    assert [p["image_id"] for p in panos] == ["pano"]


def test_raw_prediction_tables_are_append_only(store, tmp_path):
    seed_phase0(store, tmp_path)
    assert store.count("predictions_raw") == 6 and store.count("detections_raw") == 7
    before = store.one("SELECT max_animal_conf FROM predictions_raw WHERE image_id = 'img1' AND variant = 'full'")
    # A "rerun" with different numbers for the same key must not change anything.
    n_new = store.append_predictions([{
        "image_id": "img1", "model_version": "4.0.3a", "variant": "full", "run_id": "r2", "prediction": "changed",
        "prediction_score": 0.1, "prediction_source": "detector", "top5_classes": "[]", "top5_scores": "[]",
        "n_detections": 0, "max_animal_conf": 0.01, "failures": None, "raw_json": "{}",
    }])
    assert n_new == 0
    assert store.one("SELECT max_animal_conf FROM predictions_raw WHERE image_id = 'img1' AND variant = 'full'") == before
    # A new model version is a new row, not an overwrite.
    n_new = store.append_predictions([{
        "image_id": "img1", "model_version": "5.0.0", "variant": "full", "run_id": "r3", "prediction": "x",
        "prediction_score": 0.5, "prediction_source": "classifier", "top5_classes": "[]", "top5_scores": "[]",
        "n_detections": 0, "max_animal_conf": None, "failures": None, "raw_json": "{}",
    }])
    assert n_new == 1 and store.count("predictions_raw") == 7
    # The generic writer refuses replace mode on these tables outright.
    import pytest
    with pytest.raises(ValueError):
        store._write("predictions_raw", ["image_id"], [{"image_id": "z"}], mode="replace")


def test_variant_keeps_pano_slices_apart(store, tmp_path):
    seed_phase0(store, tmp_path)
    assert store.sql("SELECT variant FROM predictions_raw WHERE image_id = 'pano1'") == [("yaw090",)]
    assert store.one("SELECT count(*) FROM predictions_raw WHERE variant = 'full'") == 5


def test_reviews_and_runs(store):
    store.upsert_images([image_row("img1")])
    store.upsert_reviews([{"image_id": "img1", "det_idx": 0, "reviewer": "me", "verdict": "tp",
                           "true_species": "bison", "species_agree": "yes", "est_distance_m": 120.0, "notes": None}])
    store.upsert_reviews([{"image_id": "img1", "det_idx": 0, "reviewer": "me", "verdict": "fp",
                           "true_species": None, "species_agree": None, "est_distance_m": None, "notes": "rock"}])
    assert store.one("SELECT count(*) FROM manual_review") == 1
    assert store.sql("SELECT verdict, variant FROM manual_review") == [("fp", "full")]
    store.record_run({"run_id": "r1", "corridor": "test", "population": "perspective", "model_version": "4.0.3a",
                      "backend": "mps", "n_files": 3, "exit_code": 0})
    assert store.one("SELECT backend FROM runs WHERE run_id = 'r1'") == "mps"


def test_sightings_upsert_and_duplicate_marking(store):
    from conftest import inat_observations

    from parkwild.inaturalist import normalize
    rows = [normalize(o, "yellowstone") for o in inat_observations()]
    assert store.upsert_sightings(rows) == 3
    assert store.upsert_sightings(rows) == 3          # refresh is a replace, count unchanged
    assert store.count("sightings") == 3
    store.mark_duplicates([("inaturalist:1003", "inaturalist:1001")])
    assert store.one("SELECT duplicate_of FROM sightings WHERE sighting_id = 'inaturalist:1003'") == "inaturalist:1001"
    store.clear_duplicates("yellowstone")
    assert store.one("SELECT count(*) FROM sightings WHERE duplicate_of IS NOT NULL") == 0


def test_v2_sampler_is_stable_where_v1_was_not(store):
    """E-003: v1 (setseed + random) returned different orders on consecutive
    calls. v2 must return the identical list every time; v1 is only required
    to still run, since asserting flakiness would itself be flaky."""
    store.upsert_images([image_row(f"i{k}", sequence=f"s{k % 4}") for k in range(40)])
    picks = [[p["image_id"] for p in store.images_pending_download("test", limit=20, max_per_sequence=10)] for _ in range(5)]
    assert all(p == picks[0] for p in picks)
    legacy = store.images_pending_download_v1("test", limit=20, max_per_sequence=10)
    assert len(legacy) == 20
