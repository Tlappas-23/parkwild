import json

from conftest import write_payload
from parkwild.speciesnet_runner import build_command, display_name, parse_predictions, split_label


def test_build_command_flags(tmp_path):
    cmd = build_command(tmp_path / "imgs", tmp_path / "out.json", country="USA", admin1_region="WY", batch_size=4, python="py")
    assert cmd[:3] == ["py", "-m", "speciesnet.scripts.run_model"]
    for flag in ("--folders", "--predictions_json", "--country", "--admin1_region", "--batch_size", "--bypass_prompts"):
        assert flag in cmd
    assert cmd[cmd.index("--country") + 1] == "USA"
    assert cmd[cmd.index("--admin1_region") + 1] == "WY"
    assert "--admin1_region" not in build_command(tmp_path, tmp_path / "o.json")


def test_split_label_and_display_name():
    full = "a1b2;mammalia;cetartiodactyla;bovidae;bison;bison;american bison"
    assert split_label(full)["common_name"] == "american bison"
    assert display_name(full) == "american bison"
    rolled = "c3d4;mammalia;cetartiodactyla;cervidae;;;"
    assert display_name(rolled) == "cervidae (family)"
    assert display_name("blank") == "blank"
    assert display_name(None) == ""


def test_parse_predictions(tmp_path):
    preds, dets = parse_predictions(write_payload(tmp_path), run_id="r1")
    assert [p["image_id"] for p in preds] == ["img1", "img2", "img3"]
    p1, p2, p3 = preds
    assert p1["max_animal_conf"] == 0.88 and p1["n_detections"] == 3
    assert json.loads(p1["top5_classes"])[0].endswith("american bison")
    assert p2["max_animal_conf"] is None and p2["prediction"] == "blank"
    assert p3["failures"] is not None and p3["prediction"] is None
    assert len(dets) == 3
    assert dets[2]["category"] == "3" and dets[2]["bbox_w"] == 0.20
    assert all(d["model_version"] == "4.0.3a" for d in dets)
