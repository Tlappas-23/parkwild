#!/usr/bin/env python
"""
Decision 1's condition: before trusting any number from SpeciesNet on this
machine, run the same 20 images twice and confirm the output is identical.

FIRST VERSION ran MPS twice and CPU once. MPS segfaults past a handful of
frames (E-012), so the backend is CPU and this script now measures:

  CPU run 1 vs CPU run 2  -> must be identical. If not, every downstream
                             number needs an error bar.
  MPS (attempted)         -> recorded as ok / crashed, never required.

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
    # MPS is known to hang in some modes (E-012); never wait more than 15 minutes for it.
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"speciesnet timed out ({'cpu' if cpu else 'mps'})") from None
    if proc.returncode != 0:
        print(proc.stdout[-2000:], proc.stderr[-4000:], file=sys.stderr)
        raise SystemExit(f"speciesnet failed ({'cpu' if cpu else 'mps'}, exit {proc.returncode})")
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
    t_cpu1 = run(work / "images", work / "cpu1.json", cpu=True)
    t_cpu2 = run(work / "images", work / "cpu2.json", cpu=True)
    cpu1, cpu2 = load(work / "cpu1.json"), load(work / "cpu2.json")
    byte_identical = (work / "cpu1.json").read_bytes() == (work / "cpu2.json").read_bytes()
    mps_status: dict = {"attempted": True}
    try:
        t_mps = run(work / "images", work / "mps.json", cpu=False)
        mps = load(work / "mps.json")
        mps_status.update(ok=True, seconds=round(t_mps, 1), vs_cpu=compare(cpu1, mps, tol=1e-3))
    except SystemExit as exc:
        mps_status.update(ok=False, error=str(exc))
    report = {
        "images": [f.name for f in files],
        "seconds": {"cpu_run1": round(t_cpu1, 1), "cpu_run2": round(t_cpu2, 1)},
        "cpu_run1_vs_run2": {"byte_identical_json": byte_identical, **compare(cpu1, cpu2, tol=0.0)},
        "mps": mps_status,
    }
    cpu_deterministic = report["cpu_run1_vs_run2"]["identical_within_tol"]
    report["verdict"] = {
        "cpu_deterministic": cpu_deterministic,
        "mps_usable": bool(mps_status.get("ok")) and bool(mps_status.get("vs_cpu", {}).get("identical_within_tol")),
        "backend_to_use": "cpu",
    }
    out = ROOT / "reports" / "determinism.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["verdict"]), json.dumps(report["seconds"]))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
