import csv

from conftest import image_row, seed_phase0
from PIL import Image

from parkwild.report import cluster_detections, cluster_detections_v1, phase0_numbers, render_phase0_markdown, update_results_md, wilson
from parkwild.review import (
    BANDS,
    band_of,
    load_review_csv,
    pick_sample,
    pick_sample_uniform_v1,
    render_review_images,
    write_review_template,
)


def test_wilson_interval():
    lo, hi = wilson(9, 10)
    assert 0.59 < lo < 0.60 and 0.98 < hi < 0.99
    assert wilson(0, 0) is None
    lo, hi = wilson(0, 5)
    assert lo == 0.0 and 0.43 < hi < 0.44


def test_band_of_matches_bands():
    assert band_of(0.2) == "0.2-0.5" and band_of(0.5) == "0.5-0.8" and band_of(0.99) == "0.8-1.0"
    assert band_of(0.1) == "out" and len(BANDS) == 3


def test_stratified_sample_one_per_image_and_per_population(store, tmp_path):
    seed_phase0(store, tmp_path)
    sample = pick_sample(store, "test", n=30, min_conf=0.2)
    # perspective boxes >= 0.2: img1 (0.88), img4 (0.35, 0.62), img5 (0.55). One per image => 3 rows.
    assert sorted(s["image_id"] for s in sample) == ["img1", "img4", "img5"]
    assert {s["band"] for s in sample} <= {"0.2-0.5", "0.5-0.8", "0.8-1.0"}
    assert all(s["variant"] == "full" for s in sample)
    pano = pick_sample(store, "test", population="pano", n=30, min_conf=0.2)
    assert [(s["image_id"], s["variant"], s["band"]) for s in pano] == [("pano1", "yaw090", "0.2-0.5")]
    assert pick_sample(store, "test", n=30, min_conf=0.2) == sample   # deterministic


def test_clusters_chain_frames_but_never_merge_boxes_in_one_frame(store, tmp_path):
    seed_phase0(store, tmp_path)
    # seq-a: img1 bison (1 box) at t=0; img4 elk (2 boxes) at t=5 s; img5 elk (1 box) at t=8 s, 20 m on.
    c = cluster_detections(store, "test", min_conf=0.2)
    assert c["n_boxes"] == 4 and c["n_images"] == 3
    assert c["n_clusters"] == 2                 # bison chain, elk chain (img4 + img5)
    assert c["n_individuals_est"] == 3          # 1 bison + max(2, 1) elk
    assert abs(c["duplicate_rate"] - 0.25) < 1e-9
    c0 = cluster_detections(store, "test", min_conf=0.2, gap_s=0)
    assert c0["n_clusters"] == 3 and c0["n_individuals_est"] == 4   # no chaining => every frame its own cluster


def test_phase0_numbers_and_markdown(store, tmp_path):
    seed_phase0(store, tmp_path)
    store.upsert_reviews([
        {"image_id": "img1", "variant": "full", "det_idx": 0, "reviewer": "me", "verdict": "tp",
         "true_species": "bison", "species_agree": "yes", "est_distance_m": 150.0, "notes": None},
        {"image_id": "img4", "variant": "full", "det_idx": 1, "reviewer": "me", "verdict": "fp",
         "true_species": None, "species_agree": None, "est_distance_m": None, "notes": "shrub"},
    ])
    n = phase0_numbers(store, "test", road_km=10.0)
    assert n["population"] == "perspective" and n["recall"] == "unmeasured"
    assert n["n_indexed"] == 5 and n["n_indexed_all"] == 6 and n["n_downloaded"] == 5 and n["n_predicted"] == 5
    assert n["n_model_failures"] == 1
    assert n["images_with_animal"][0.2]["count"] == 3 and n["images_with_animal"][0.8]["count"] == 1
    assert n["images_with_animal"][0.2]["ci"] is not None
    assert n["images_with_vehicle"] == 1
    assert n["review"]["precision"] == 0.5 and n["review"]["precision_ci"] is not None
    assert n["review"]["by_band"]["0.8-1.0"]["tp"] == 1 and n["review"]["by_band"]["0.5-0.8"]["fp"] == 1
    assert n["review"]["distances_m"]["max"] == 150.0
    assert n["images_per_road_km"] == 0.6
    md = render_phase0_markdown(n)
    assert "american bison (1)" in md and "| >= 0.2 | 3 | 60.0% (95% CI" in md and "recall: unmeasured" in md

    p = phase0_numbers(store, "test", population="pano")
    assert p["n_indexed"] == 1 and p["n_predicted"] == 1 and p["images_with_animal"][0.2]["count"] == 1


def test_report_refuses_to_mix_reviewers(store, tmp_path):
    seed_phase0(store, tmp_path)
    for who, verdict in (("me", "tp"), ("claude", "fp")):
        store.upsert_reviews([{"image_id": "img1", "variant": "full", "det_idx": 0, "reviewer": who, "verdict": verdict,
                               "true_species": "bison" if verdict == "tp" else "rock", "species_agree": "yes" if verdict == "tp" else None,
                               "est_distance_m": None, "notes": None}])
    import pytest
    with pytest.raises(ValueError):
        phase0_numbers(store, "test")
    assert phase0_numbers(store, "test", reviewer="me")["review"]["tp"] == 1
    assert phase0_numbers(store, "test", reviewer="claude")["review"]["fp"] == 1


def test_update_results_md_is_idempotent(tmp_path):
    path = tmp_path / "RESULTS.md"
    path.write_text("# RESULTS\n\nhand-written intro\n")
    update_results_md(path, "phase0:test:perspective", "first", heading="### T")
    update_results_md(path, "phase0:test:perspective", "second")
    text = path.read_text()
    assert "hand-written intro" in text and "### T" in text
    assert text.count("<!-- phase0:test:perspective:start -->") == 1
    assert "second" in text and "first" not in text


def test_review_csv_roundtrip(store, tmp_path):
    seed_phase0(store, tmp_path)
    sample = pick_sample(store, "test", n=30, min_conf=0.2)
    csv_path = tmp_path / "review.csv"
    write_review_template(sample, csv_path)
    rows = list(csv.DictReader(open(csv_path)))
    assert {r["predicted"] for r in rows} == {"american bison", "elk"} and rows[0]["verdict"] == ""
    assert rows[0]["variant"] == "full" and rows[0]["band"] in {"0.2-0.5", "0.5-0.8", "0.8-1.0"}
    assert load_review_csv(csv_path) == []                     # nothing judged yet

    rows[0].update(verdict="TP", true_species="bison", species_agree="yes", est_distance_m="120")
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    loaded = load_review_csv(csv_path)
    assert loaded[0]["verdict"] == "tp" and loaded[0]["est_distance_m"] == 120.0 and loaded[0]["variant"] == "full"
    store.upsert_reviews(loaded)
    assert store.one("SELECT count(*) FROM manual_review") == 1


def test_render_review_images_applies_exif_orientation(store, tmp_path):
    """A JPEG tagged orientation=3 (180 degrees) must be drawn upright, the way
    SpeciesNet saw it, so a box in the bottom-right lands on the red quadrant."""
    im = Image.new("RGB", (400, 200), "white")
    im.paste((255, 0, 0), (0, 0, 200, 100))            # red top-left in stored pixels...
    exif = Image.Exif()
    exif[0x0112] = 3                                    # ...which is bottom-right once rotated
    path = tmp_path / "img1.jpg"
    im.save(path, exif=exif.tobytes())

    store.upsert_images([image_row("img1")])
    store.record_download({"image_id": "img1", "local_path": str(path), "size_kind": "original", "error": None})
    store.append_predictions([{"image_id": "img1", "model_version": "m", "variant": "full", "run_id": "r", "prediction": "x",
                               "prediction_score": 0.9, "prediction_source": "classifier", "top5_classes": "[]",
                               "top5_scores": "[]", "n_detections": 1, "max_animal_conf": 0.9, "failures": None, "raw_json": "{}"}])
    store.append_detections([{"image_id": "img1", "model_version": "m", "variant": "full", "det_idx": 0, "category": "1", "label": "animal",
                              "conf": 0.9, "bbox_x": 0.5, "bbox_y": 0.5, "bbox_w": 0.5, "bbox_h": 0.5}])
    sample = pick_sample(store, "test", n=1)
    render_review_images(store, sample, tmp_path / "out", crop_pad=0.0)

    crop = Image.open(tmp_path / "out" / "img1_full_0_crop.jpg")
    r, g, b = crop.getpixel((crop.width // 2, crop.height // 2))
    assert r > 200 and g < 80 and b < 80, "crop centre should be the red quadrant after EXIF transpose"
    assert (tmp_path / "out" / "img1_full_0_frame.jpg").exists()


def test_v1_clusters_undercount_boxes_in_one_frame(store, tmp_path):
    """The comparison behind E-007. v1 merges the two elk boxes in img4 into
    one; v2 keeps them as two individuals. If v1 ever matches v2 here the
    fixture has lost its two-box frame."""
    seed_phase0(store, tmp_path)
    v1 = cluster_detections_v1(store, "test", min_conf=0.2)
    v2 = cluster_detections(store, "test", min_conf=0.2)
    assert v1["n_boxes"] == v2["n_boxes"] == 4
    assert v1["n_individuals_est"] < v2["n_individuals_est"]
    assert v2["n_individuals_est"] == 3 and v1["n_individuals_est"] == 2


def _skewed_population(store, n_low=60, n_mid=12, n_high=6):
    """Many low-confidence boxes, few high: what a detector on out-of-domain
    frames actually produces."""
    rows, preds, dets = [], [], []
    k = 0
    for band, count in (((0.2, 0.5), n_low), ((0.5, 0.8), n_mid), ((0.8, 1.01), n_high)):
        for j in range(count):
            iid = f"s{k}"
            k += 1
            conf = band[0] + (min(band[1], 1.0) - band[0]) * (j + 0.5) / count
            rows.append(image_row(iid, sequence=f"q{k % 7}"))
            store.record_download({"image_id": iid, "local_path": f"/x/{iid}.jpg", "size_kind": "original", "error": None})
            preds.append({"image_id": iid, "model_version": "m", "variant": "full", "run_id": "r", "prediction": "x",
                          "prediction_score": 0.5, "prediction_source": "classifier", "top5_classes": "[]", "top5_scores": "[]",
                          "n_detections": 1, "max_animal_conf": conf, "failures": None, "raw_json": "{}"})
            dets.append({"image_id": iid, "model_version": "m", "variant": "full", "det_idx": 0, "category": "1", "label": "animal",
                         "conf": conf, "bbox_x": 0.1, "bbox_y": 0.1, "bbox_w": 0.1, "bbox_h": 0.1})
    store.upsert_images(rows)
    store.append_predictions(preds)
    store.append_detections(dets)


def test_stratified_beats_uniform_on_a_skewed_population(store):
    """The comparison behind ADR-0010: v1 follows the population skew, v2 gives
    every band its share so the high band has a usable n."""
    _skewed_population(store)
    from collections import Counter
    v1 = Counter(s["band"] for s in pick_sample_uniform_v1(store, "test", n=30))
    v2 = Counter(s["band"] for s in pick_sample(store, "test", n=30))
    assert sum(v1.values()) == 30
    # 60 of 78 candidates are low-band, so a uniform draw of 30 lands ~23 there.
    assert v1["0.2-0.5"] >= 15, f"uniform sample should be dominated by the low band: {v1}"
    # v2 asks for 10 per band; the high band only has 6, and is left short, not back-filled.
    assert v2 == Counter({"0.2-0.5": 10, "0.5-0.8": 10, "0.8-1.0": 6})
    assert v2["0.8-1.0"] > v1["0.8-1.0"]
