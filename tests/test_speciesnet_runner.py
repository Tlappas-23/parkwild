import json

import pytest
from conftest import write_payload

from parkwild.contracts import ContractError
from parkwild.speciesnet_runner import build_command, display_name, parse_predictions, split_label, split_stem


def test_build_command_uses_repo_relative_paths():
    """E-016: SpeciesNet resumes only if the folder string matches the one in the
    JSON. Paths inside the repo are always passed relative to the repo root."""
    from parkwild.speciesnet_runner import ROOT
    cmd = build_command(ROOT / "data" / "images" / "x", ROOT / "data" / "predictions" / "x.json", python="py")
    assert cmd[cmd.index("--folders") + 1] == "data/images/x"
    assert cmd[cmd.index("--predictions_json") + 1] == "data/predictions/x.json"


def test_build_command_flags(tmp_path):
    cmd = build_command(tmp_path / "imgs", tmp_path / "out.json", country="USA", admin1_region="WY", batch_size=4, python="py")
    assert cmd[:3] == ["py", "-m", "speciesnet.scripts.run_model"]
    for flag in ("--folders", "--predictions_json", "--country", "--admin1_region", "--batch_size", "--bypass_prompts"):
        assert flag in cmd
    assert cmd[cmd.index("--country") + 1] == "USA"
    assert cmd[cmd.index("--admin1_region") + 1] == "WY"
    assert "--admin1_region" not in build_command(tmp_path, tmp_path / "o.json")
    cpu = build_command(tmp_path, tmp_path / "o.json", python="py", force_cpu=True)
    assert cpu[1].endswith("scripts/speciesnet_cpu.py") and "-m" not in cpu[:2]


def test_split_label_and_display_name():
    full = "a1b2;mammalia;cetartiodactyla;bovidae;bison;bison;american bison"
    assert split_label(full)["common_name"] == "american bison"
    assert display_name(full) == "american bison"
    rolled = "c3d4;mammalia;cetartiodactyla;cervidae;;;"
    assert display_name(rolled) == "cervidae (family)"
    assert display_name("blank") == "blank"
    assert display_name(None) == ""


def test_split_stem_variants():
    assert split_stem("/a/b/123.jpg") == ("123", "full")
    assert split_stem("/a/b/123__yaw090.jpg") == ("123", "yaw090")


def test_parse_predictions(tmp_path):
    preds, dets = parse_predictions(write_payload(tmp_path), run_id="r1")
    expected = [("img1", "full"), ("img2", "full"), ("img3", "full"), ("img4", "full"), ("img5", "full"), ("pano1", "yaw090")]
    assert [(p["image_id"], p["variant"]) for p in preds] == expected
    p1, p2, p3 = preds[:3]
    assert p1["max_animal_conf"] == 0.88 and p1["n_detections"] == 3
    assert json.loads(p1["top5_classes"])[0].endswith("american bison")
    assert p2["max_animal_conf"] is None and p2["prediction"] == "blank"
    assert p3["failures"] is not None and p3["prediction"] is None
    assert len(dets) == 7
    assert dets[2]["category"] == "3" and dets[2]["bbox_w"] == 0.20
    assert dets[-1]["variant"] == "yaw090"


def test_parse_rejects_pixel_boxes(tmp_path):
    p = tmp_path / "bad.json"
    payload = {"predictions": [{"filepath": "x.jpg", "model_version": "m",
                                "detections": [{"category": "1", "label": "animal", "conf": 0.5, "bbox": [120, 80, 40, 30]}]}]}
    p.write_text(json.dumps(payload))
    with pytest.raises(ContractError):
        parse_predictions(p, run_id="r")
