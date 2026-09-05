"""
Run SpeciesNet (MegaDetector + species classifier + ensemble) and turn its
JSON into table rows.

I shell out to `python -m speciesnet.scripts.run_model` instead of importing
the package. Two reasons:

1. It keeps torch out of this package's import graph, so the crawler, the tests
   and the notebook all work in the light venv without the ML install.
2. SpeciesNet's CLI already resumes: given an existing --predictions_json it
   reloads finished predictions and only processes new files. That is exactly
   the "never re-run inference on an image already processed" rule from the
   brief, for free.

Flag names below were checked against speciesnet/scripts/run_model.py
(package version 5.0.5, 2026-09-05).
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# SpeciesNet's own detector threshold is 0.01, i.e. it returns nearly every box
# and leaves thresholding to the caller. 0.2 is the Phase 0 reporting cut.
ANIMAL_CATEGORY = "1"
HUMAN_CATEGORY = "2"
VEHICLE_CATEGORY = "3"
DEFAULT_REPORT_THRESHOLD = 0.2


def speciesnet_available(python: str = sys.executable) -> bool:
    """True if `import speciesnet` works in the given interpreter."""
    proc = subprocess.run([python, "-c", "import speciesnet"], capture_output=True)
    return proc.returncode == 0


def build_command(
    image_dir: Path,
    predictions_json: Path,
    *,
    country: str = "USA",
    admin1_region: str | None = None,
    batch_size: int = 8,
    python: str = sys.executable,
    extra_args: tuple[str, ...] = (),
) -> list[str]:
    """The exact CLI invocation. Kept separate from run() so tests can check it
    and so I can print it for a manual run on Kaggle."""
    cmd = [
        python, "-m", "speciesnet.scripts.run_model",
        "--folders", str(image_dir),
        "--predictions_json", str(predictions_json),
        "--country", country,          # ISO 3166-1 alpha-3; geofence drops species absent from the USA
        "--batch_size", str(batch_size),
        "--bypass_prompts",            # never block a batch job on a y/n question
    ]
    if admin1_region:
        cmd += ["--admin1_region", admin1_region]  # e.g. WY; tightens the geofence to the state
    cmd += list(extra_args)
    return cmd


def run_speciesnet(image_dir: Path, predictions_json: Path, **kwargs) -> int:
    """Run the full ensemble over every image in `image_dir`. Returns the exit
    code. Output streams straight to the terminal so progress bars work."""
    python = kwargs.get("python", sys.executable)
    if not speciesnet_available(python):
        raise RuntimeError(
            f"speciesnet is not importable from {python}. Install the ML extras first "
            "(`make setup-ml`, which pulls PyTorch and ~1 GB of weights) or point --python at an env that has it."
        )
    predictions_json.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(image_dir, predictions_json, **kwargs)
    log.info("running: %s", " ".join(cmd))
    return subprocess.run(cmd).returncode


# ---- output parsing ----------------------------------------------------------

LABEL_PARTS = ("uuid", "class", "order", "family", "genus", "species", "common_name")


def split_label(label: str | None) -> dict[str, str]:
    """SpeciesNet labels are 7 semicolon-separated parts:
    uuid;class;order;family;genus;species;common_name. Rolled-up predictions
    leave the lower ranks empty ("...;cervidae;;;deer family"). Anything that
    isn't 7 parts (e.g. 'blank', 'unknown') is returned under 'raw'."""
    if not label:
        return {"raw": ""}
    parts = label.split(";")
    if len(parts) != len(LABEL_PARTS):
        return {"raw": label}
    return dict(zip(LABEL_PARTS, parts))


def display_name(label: str | None) -> str:
    """Short human-readable name: common name if present, else the deepest
    non-empty taxonomic rank, else the raw string."""
    parts = split_label(label)
    if "raw" in parts:
        return parts["raw"]
    if parts["common_name"]:
        return parts["common_name"]
    for rank in ("species", "genus", "family", "order", "class"):
        if parts[rank]:
            return f"{parts[rank]} ({rank})"
    return label or ""


def image_id_from_path(filepath: str) -> str:
    """Images are saved as <image_id>.jpg, so the stem is the Mapillary ID."""
    return Path(filepath).stem


def parse_predictions(predictions_json: Path, *, run_id: str) -> tuple[list[dict], list[dict]]:
    """Read SpeciesNet's output and return (prediction_rows, detection_rows)
    ready for Store.upsert_predictions / upsert_detections.

    Every detection SpeciesNet emitted is kept, down to its 0.01 floor. Filtering
    happens at query time so I can re-evaluate thresholds without re-running.
    """
    with open(predictions_json) as fh:
        payload = json.load(fh)
    prediction_rows: list[dict] = []
    detection_rows: list[dict] = []
    for item in payload.get("predictions", []):
        image_id = image_id_from_path(item["filepath"])
        model_version = str(item.get("model_version") or "unknown")
        detections = item.get("detections") or []
        animal_confs = [d["conf"] for d in detections if str(d.get("category")) == ANIMAL_CATEGORY]
        classifications = item.get("classifications") or {}
        prediction_rows.append(
            {
                "image_id": image_id,
                "model_version": model_version,
                "run_id": run_id,
                "prediction": item.get("prediction"),
                "prediction_score": item.get("prediction_score"),
                "prediction_source": item.get("prediction_source"),
                "top5_classes": json.dumps(classifications.get("classes", [])),
                "top5_scores": json.dumps(classifications.get("scores", [])),
                "n_detections": len(detections),
                "max_animal_conf": max(animal_confs) if animal_confs else None,
                "failures": json.dumps(item["failures"]) if item.get("failures") else None,
                "raw_json": json.dumps(item, separators=(",", ":")),
            }
        )
        for idx, det in enumerate(detections):
            x, y, w, h = det.get("bbox", [None, None, None, None])
            detection_rows.append(
                {
                    "image_id": image_id,
                    "model_version": model_version,
                    "det_idx": idx,
                    "category": str(det.get("category")),
                    "label": det.get("label"),
                    "conf": det.get("conf"),
                    "bbox_x": x, "bbox_y": y, "bbox_w": w, "bbox_h": h,
                }
            )
    return prediction_rows, detection_rows
