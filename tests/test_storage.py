from conftest import image_row


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
    store.clear_tiles("test")
    assert store.done_tile_ids("test") == set()


def test_pending_download_spreads_across_sequences_and_skips_pano_and_done(store):
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
    assert [p["image_id"] for p in again] == [p["image_id"] for p in picked]   # seeded => reproducible

    with_pano = store.images_pending_download("test", limit=100, max_per_sequence=3, exclude_pano=False)
    assert "pano" in {p["image_id"] for p in with_pano}


def test_predictions_and_reviews_roundtrip(store):
    store.upsert_images([image_row("img1")])
    store.upsert_predictions([{
        "image_id": "img1", "model_version": "4.0.3a", "run_id": "r1", "prediction": "x",
        "prediction_score": 0.9, "prediction_source": "classifier", "top5_classes": "[]", "top5_scores": "[]",
        "n_detections": 1, "max_animal_conf": 0.88, "failures": None, "raw_json": "{}",
    }])
    store.upsert_detections([{
        "image_id": "img1", "model_version": "4.0.3a", "det_idx": 0, "category": "1", "label": "animal",
        "conf": 0.88, "bbox_x": 0.1, "bbox_y": 0.2, "bbox_w": 0.05, "bbox_h": 0.04,
    }])
    store.upsert_reviews([{"image_id": "img1", "det_idx": 0, "reviewer": "me", "verdict": "tp",
                           "true_species": "bison", "species_agree": "yes", "est_distance_m": 120.0, "notes": None}])
    store.upsert_reviews([{"image_id": "img1", "det_idx": 0, "reviewer": "me", "verdict": "fp",
                           "true_species": None, "species_agree": None, "est_distance_m": None, "notes": "rock"}])
    assert store.one("SELECT count(*) FROM manual_review") == 1
    assert store.one("SELECT verdict FROM manual_review") == "fp"
    # raw prediction untouched by the review
    assert store.one("SELECT max_animal_conf FROM predictions_raw") == 0.88
