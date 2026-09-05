#!/usr/bin/env python
"""
Decision 1's condition: before trusting any number from SpeciesNet on this
machine, run the same 20 images twice on MPS and once on CPU.

  MPS run 1 vs MPS run 2  -> must be identical. If not, the backend is
                             nondeterministic and every downstream number
                             needs an error bar.
  MPS vs CPU              -> should agree on labels and boxes to a few decimals.
                             Silent disagreement means MPS is producing wrong
                             output rather than failing, and CPU is the backend.

Writes reports/determinism.json and prints a verdict. Runs standalone, no DB.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from parkwild.config import IMAGES_DIR  # noqa: E402

# N_IMAGES — BORROWED (decision 1: "run 20 images twice")
N_IMAGES = 20


def run(image_dir: Path, out: Path, *, cpu: bool) -> float:
    cmd = [sys.executable] + (["scripts/speciesnet_cpu.py"] if cpu else ["-m", "speciesnet.scripts.run_model"])
    cmd += ["--folders", str(image_dir), "--predictions_json", str(out), "--country", "USA", "--admin1_region", "WY",
            "--batch_size", "8", "--bypass_prompts"]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout[-2000:], proc.stderr[-4000:], file=sys.stderr)
        raise SystemExit(f"speciesnet failed ({'cpu' if cpu else 'mps'})")
    return time.time() - t0


def load(path: Path) -> dict[str, dict]:
    preds = json.loads(path.read_text())["predictions"]
    return {Path(p["filepath"]).name: p for p in preds}


def compare(a: dict, b: dict, *, tol: float) -> dict:
    """Per-image comparison: same final label? same box count? max abs diff in scores."""
    label_mismatch, box_count_mismatch, max_score_diff, max_box_diff = [], [], 0.0, 0.0
    for name, pa in a.items():
        pb = b[name]
        if pa.get("prediction") != pb.get("prediction"):
            label_mismatch.append(name)
        da, db = pa.get("detections", []), pb.get("detections", [])
        if len(da) != len(db):
            box_count_mismatch.append(name)
        for x, y in zip(da, db):
            max_score_diff = max(max_score_diff, abs(x["conf"] - y["conf"]))
            max_box_diff = max(max_box_diff, max(abs(u - v) for u, v in zip(x["bbox"], y["bbox"])))
        sa, sb = pa.get("classifications", {}).get("scores", []), pb.get("classifications", {}).get("scores", [])
        for u, v in zip(sa, sb):
            max_score_diff = max(max_score_diff, abs(u - v))
    return {
        "n": len(a), "label_mismatch": label_mismatch, "box_count_mismatch": box_count_mismatch,
        "max_score_diff": max_score_diff, "max_box_diff": max_box_diff,
        "identical_within_tol": not label_mismatch and not box_count_mismatch and max_score_diff <= tol and max_box_diff <= tol,
    }


def main() -> None:
    src = IMAGES_DIR / "lamar_valley"
    files = sorted(src.glob("*.jpg"))[:N_IMAGES]      # first 20 by name: fixed, reproducible
    work = ROOT / "data" / "determinism"
    shutil.rmtree(work, ignore_errors=True)
    (work / "images").mkdir(parents=True)
    # Copies, not symlinks: the first attempt symlinked and SpeciesNet's folder
    # scan produced a crash-shaped log with zero predictions (E-010).
    for f in files:
        shutil.copy2(f, work / "images" / f.name)
    t_mps1 = run(work / "images", work / "mps1.json", cpu=False)
    t_mps2 = run(work / "images", work / "mps2.json", cpu=False)
    t_cpu = run(work / "images", work / "cpu.json", cpu=True)
    mps1, mps2, cpu = load(work / "mps1.json"), load(work / "mps2.json"), load(work / "cpu.json")
    byte_identical = (work / "mps1.json").read_bytes() == (work / "mps2.json").read_bytes()
    report = {
        "images": [f.name for f in files],
        "seconds": {"mps_run1": round(t_mps1, 1), "mps_run2": round(t_mps2, 1), "cpu": round(t_cpu, 1)},
        "mps_run1_vs_run2": {"byte_identical_json": byte_identical, **compare(mps1, mps2, tol=0.0)},
        "mps_vs_cpu": compare(mps1, cpu, tol=1e-3),
    }
    mps_deterministic = report["mps_run1_vs_run2"]["identical_within_tol"]
    mps_agrees_cpu = report["mps_vs_cpu"]["identical_within_tol"]
    report["verdict"] = {
        "mps_deterministic": mps_deterministic,
        "mps_agrees_with_cpu": mps_agrees_cpu,
        "backend_to_use": "mps" if (mps_deterministic and mps_agrees_cpu) else "cpu",
    }
    out = ROOT / "reports" / "determinism.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["verdict"]), json.dumps(report["seconds"]))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
