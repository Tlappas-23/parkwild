"""Run SpeciesNet (MegaDetector + classifier + ensemble) and parse its JSON.

PROBLEM: get camera-trap models to score street-level frames without
dragging PyTorch into every test and notebook, and without ever scoring an
image twice.

FIRST PLAN: import the speciesnet package and call its classes. Rejected
before writing: it would put torch on the import path of the crawler and
the tests, and it would lose SpeciesNet's own resume-from-JSON behaviour.

CURRENT: shell out to `python -m speciesnet.scripts.run_model` (flags checked
against run_model.py in 5.0.5), parse the JSON into rows, contract-check
that boxes are normalised. Backend: **CPU**, by measurement (E-012). MPS
agreed with CPU exactly on three frames, then segfaulted at 20 frames in the
classifier preprocessing at batch 8 and aborted at batch 1; multi-process
mode hung. `scripts/speciesnet_cpu.py` hides MPS from torch and
`runs.backend` records what ran. Cost: CPU inference on 400 originals is on
the order of half an hour instead of ten minutes.

RESOLVED: the ensemble label "no cv result" is SpeciesNet's UNKNOWN constant
(constants.py), the fallback when neither classifier nor detector clears
its threshold. Displayed as "unknown"; its detections are still stored.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from .contracts import check_bbox_normalized

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]


def _rel(path: Path) -> str:
    """Repo-relative form of a path (or the path unchanged if outside the repo)."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


# CPU_WRAPPER — DERIVED (repo-relative path to scripts/speciesnet_cpu.py, the MPS-hiding wrapper)
CPU_WRAPPER = Path(__file__).resolve().parents[2] / "scripts" / "speciesnet_cpu.py"

# ANIMAL_CATEGORY / HUMAN_CATEGORY / VEHICLE_CATEGORY — BORROWED
# (speciesnet/constants.py, Detection enum: "1" animal, "2" human, "3" vehicle)
ANIMAL_CATEGORY = "1"
HUMAN_CATEGORY = "2"
VEHICLE_CATEGORY = "3"

# DEFAULT_REPORT_THRESHOLD — BORROWED (the brief: "above 0.2 confidence")
# Only a reporting cut. Every box SpeciesNet emits (its own floor is 0.01)
# is stored, so the threshold can move without re-running inference.
# REVISIT IF: the stratified review's precision-by-band curve says the useful
#   operating point is elsewhere; then a UI_THRESHOLD is set from that curve.
DEFAULT_REPORT_THRESHOLD = 0.2


def speciesnet_available(python: str = sys.executable) -> bool:
    """True if `import speciesnet` works in the given interpreter."""
    proc = subprocess.run([python, "-c", "import speciesnet"], capture_output=True)
    return proc.returncode == 0


def speciesnet_env_info(python: str = sys.executable) -> dict[str, str]:
    """Version and torch backend of the interpreter that will run inference, for
    the `runs` table. Best effort: 'unknown' if anything fails."""
    code = (
        "import json, importlib.metadata as m\n"
        "try:\n import torch; b='cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu')\n"
        "except Exception: b='unknown'\n"
        "try: v=m.version('speciesnet')\n"
        "except Exception: v='unknown'\n"
        "print(json.dumps({'speciesnet_version': v, 'backend': b}))"
    )
    try:
        out = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=120).stdout.strip()
        return json.loads(out.splitlines()[-1])
    except Exception:
        return {"speciesnet_version": "unknown", "backend": "unknown"}


def build_command(
    image_dir: Path,
    predictions_json: Path,
    *,
    country: str = "USA",
    admin1_region: str | None = None,
    batch_size: int = 8,
    python: str = sys.executable,
    extra_args: tuple[str, ...] = (),
    force_cpu: bool = False,
) -> list[str]:
    """The exact CLI invocation. Kept separate from run() so tests can check it
    and so I can print it for a manual run on Kaggle. `force_cpu` routes
    through scripts/speciesnet_cpu.py, which hides MPS from torch (E-012)."""
    entry = [str(CPU_WRAPPER)] if force_cpu else ["-m", "speciesnet.scripts.run_model"]
    # Paths relative to the repo root, always. SpeciesNet's resume compares the
    # filepaths stored in predictions_json with the instances it is given as
    # literal strings; an absolute folder on one run and a relative one on the
    # next made it refuse to resume (E-016). run() sets cwd=ROOT to match.
    cmd = [
        python, *entry,
        "--folders", _rel(image_dir),
        "--predictions_json", _rel(predictions_json),
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
    return subprocess.run(cmd, cwd=ROOT).returncode


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
    if parts[1] == "no cv result":   # SpeciesNet's UNKNOWN sentinel wears the 7-part shape
        return {"raw": "unknown"}
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


def split_stem(filepath: str) -> tuple[str, str]:
    """Whole frames are saved as <image_id>.jpg and panorama slices as
    <image_id>__<variant>.jpg. Returns (image_id, variant)."""
    stem = Path(filepath).stem
    if "__" in stem:
        image_id, variant = stem.split("__", 1)
        return image_id, variant
    return stem, "full"


def image_id_from_path(filepath: str) -> str:
    return split_stem(filepath)[0]


def parse_predictions(predictions_json: Path, *, run_id: str) -> tuple[list[dict], list[dict]]:
    """Read SpeciesNet's output and return (prediction_rows, detection_rows)
    ready for Store.append_predictions / append_detections.

    Every detection SpeciesNet emitted is kept, down to its 0.01 floor. Filtering
    happens at query time so I can re-evaluate thresholds without re-running.
    Boxes are contract-checked to be normalised before they reach the store.
    """
    with open(predictions_json) as fh:
        payload = json.load(fh)
    prediction_rows: list[dict] = []
    detection_rows: list[dict] = []
    for item in payload.get("predictions", []):
        image_id, variant = split_stem(item["filepath"])
        model_version = str(item.get("model_version") or "unknown")
        detections = item.get("detections") or []
        animal_confs = [d["conf"] for d in detections if str(d.get("category")) == ANIMAL_CATEGORY]
        classifications = item.get("classifications") or {}
        prediction_rows.append(
            {
                "image_id": image_id,
                "model_version": model_version,
                "variant": variant,
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
                    "variant": variant,
                    "det_idx": idx,
                    "category": str(det.get("category")),
                    "label": det.get("label"),
                    "conf": det.get("conf"),
                    "bbox_x": x, "bbox_y": y, "bbox_w": w, "bbox_h": h,
                }
            )
    check_bbox_normalized(detection_rows)
    return prediction_rows, detection_rows
