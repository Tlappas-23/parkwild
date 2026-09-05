import csv

from conftest import image_row, write_payload
from parkwild.report import phase0_numbers, render_phase0_markdown, update_results_md
from parkwild.review import load_review_csv, pick_sample, write_review_template
from parkwild.speciesnet_runner import parse_predictions


def seed(store, tmp_path):
    store.upsert_images([image_row("img1"), image_row("img2", sequence="s2"), image_row("img3", sequence="s3")])
    for i in (1, 2, 3):
        store.record_download({"image_id": f"img{i}", "local_path": f"/x/img{i}.jpg", "size_kind": "original", "error": None})
    preds, dets = parse_predictions(write_payload(tmp_path), run_id="r1")
    store.upsert_predictions(preds)
    store.upsert_detections(dets)


def test_phase0_numbers_and_markdown(store, tmp_path):
    seed(store, tmp_path)
    store.upsert_reviews([{"image_id": "img1", "det_idx": 0, "reviewer": "me", "verdict": "tp",
                           "true_species": "bison", "species_agree": "yes", "est_distance_m": 150.0, "notes": None}])
    n = phase0_numbers(store, "test", road_km=10.0)
    assert n["n_indexed"] == 3 and n["n_downloaded"] == 3 and n["n_predicted"] == 3
    assert n["n_model_failures"] == 1
    assert n["images_with_animal"][0.2]["count"] == 1
    assert abs(n["images_with_animal"][0.2]["frac"] - 1 / 3) < 1e-9
    assert n["images_with_vehicle"] == 1
    assert n["review"]["precision"] == 1.0
    assert n["review"]["distances_m"]["max"] == 150.0
    assert n["review"]["species"]["exact"] == 1
    assert n["images_per_road_km"] == 0.3
    md = render_phase0_markdown(n)
    assert "american bison (1)" in md and "| >= 0.2 | 1 | 33.3% |" in md


def test_update_results_md_is_idempotent(tmp_path):
    path = tmp_path / "RESULTS.md"
    path.write_text("# RESULTS\n\nhand-written intro\n")
    update_results_md(path, "test", "first")
    update_results_md(path, "test", "second")
    text = path.read_text()
    assert "hand-written intro" in text
    assert text.count("<!-- phase0:test:start -->") == 1
    assert "second" in text and "first" not in text


def test_pick_sample_one_per_image_and_review_csv_roundtrip(store, tmp_path):
    seed(store, tmp_path)
    sample = pick_sample(store, "test", n=30, min_conf=0.2)
    assert [s["image_id"] for s in sample] == ["img1"]          # only img1 has an animal box >= 0.2
    assert sample[0]["det_idx"] == 0 and sample[0]["conf"] == 0.88
    assert pick_sample(store, "test", n=30, min_conf=0.1)[0]["image_id"] == "img1"  # still one row per image

    csv_path = tmp_path / "review.csv"
    write_review_template(sample, csv_path)
    rows = list(csv.DictReader(open(csv_path)))
    assert rows[0]["predicted"] == "american bison" and rows[0]["verdict"] == ""
    assert load_review_csv(csv_path) == []                     # nothing judged yet

    rows[0].update(verdict="TP", true_species="bison", species_agree="yes", est_distance_m="120")
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    loaded = load_review_csv(csv_path)
    assert loaded[0]["verdict"] == "tp" and loaded[0]["est_distance_m"] == 120.0
    store.upsert_reviews(loaded)
    assert store.one("SELECT count(*) FROM manual_review") == 1
