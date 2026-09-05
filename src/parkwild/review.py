"""The manual-inspection set for Phase 0.

PROBLEM: the only honest precision number comes from a human looking at
boxes. Which boxes get looked at decides what the number means.

FIRST ATTEMPT: uniform random over all boxes above the threshold, one per
frame. Kept as `pick_sample_uniform_v1`. Its sample follows the population,
and the population is dominated by the 0.2 to 0.5 band, so the high band
that a UI threshold would actually use gets two or three boxes and no usable
precision estimate. (Top-N by confidence, the other obvious choice, inflates
precision; the build spec forbids it and it was never implemented.)

CURRENT: equal allocation across three detector-confidence bands, one box
per frame, order from a seeded hash so the sample is reproducible. Bands
short of their quota stay short and are reported, never back-filled from an
easier band. tests/test_report_and_review.py::test_stratified_beats_uniform_
on_a_skewed_population shows the difference on a synthetic population.

CONSIDERED, NOT DONE: stratifying by predicted species as well. Largest
per-species n in a 30-box sample would be single digits; nothing to learn.

UNRESOLVED: 30 boxes gives a precision interval roughly ±17 points at 50%.
The Wilson interval in report.py says so; more boxes is the only fix.
"""
from __future__ import annotations

import csv
import json
import logging
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .decisionlog import log_filter
from .pano import slice_path_for
from .speciesnet_runner import ANIMAL_CATEGORY, display_name
from .storage import VARIANT_FILTER, Store

log = logging.getLogger(__name__)

# BANDS — ASSUMED (three bands per BUILD_SPEC.md; the cut points are mine)
# 0.2 is the brief's reporting threshold. 0.5 and 0.8 split the rest into a
# "maybe" and a "confident" band of roughly comparable population on camera-trap
# data; whether that holds on street-level frames is exactly what the review
# measures. The upper bound 1.01 keeps conf == 1.0 in the top band.
# REVISIT IF: a band ends up with under 5 boxes after the review, or the
#   precision-by-band curve suggests a different knee.
BANDS = ((0.2, 0.5), (0.5, 0.8), (0.8, 1.01))

REVIEW_COLUMNS = [
    # filled by the script
    "image_id", "variant", "det_idx", "band", "conf", "predicted", "prediction_score", "prediction_source",
    "top5", "source_url", "frame_file", "crop_file",
    # filled by me
    "verdict",          # tp | fp | unsure
    "true_species",     # what it actually is: the species for a tp; for a fp, the thing (rock, shrub, log, vehicle, person, shadow, sign)
    "species_agree",    # yes | rollup | no | na   (rollup = model gave a correct coarser taxon)
    "est_distance_m",   # rough range from camera to animal, metres
    "notes",
]


def band_of(conf: float) -> str:
    for lo, hi in BANDS:
        if lo <= conf < hi:
            return f"{lo:.1f}-{min(hi, 1.0):.1f}"
    return "out"


def _candidates(store: Store, corridor: str, population: str, min_conf: float, seed: int) -> list[dict]:
    rows = store.sql(
        f"""
        SELECT d.image_id, d.model_version, d.variant, d.det_idx, d.conf,
               d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h,
               p.prediction, p.prediction_score, p.prediction_source, p.top5_classes,
               dl.local_path, i.source_url
        FROM detections_raw d
        JOIN predictions_raw p USING (image_id, model_version, variant)
        JOIN downloads dl USING (image_id)
        JOIN images i USING (image_id)
        WHERE i.corridor = ? AND d.category = ? AND d.conf >= ? AND dl.error IS NULL
          AND d.{VARIANT_FILTER[population]}
        ORDER BY hash(d.image_id || ':' || d.variant || ':' || CAST(d.det_idx AS VARCHAR) || ':' || ?)
        """,
        [corridor, ANIMAL_CATEGORY, min_conf, str(seed)],
    )
    keys = [
        "image_id", "model_version", "variant", "det_idx", "conf", "bbox_x", "bbox_y", "bbox_w", "bbox_h",
        "prediction", "prediction_score", "prediction_source", "top5_classes", "local_path", "source_url",
    ]
    return [dict(zip(keys, r)) for r in rows]


def pick_sample_uniform_v1(store: Store, corridor: str, *, population: str = "perspective", n: int = 30,
                           min_conf: float = 0.2, seed: int = 42) -> list[dict]:
    """SUPERSEDED 2026-09-05 by pick_sample(). Kept for comparison.

    Uniform random over boxes above min_conf, one per frame. Follows the
    population's confidence distribution, which is bottom-heavy, so the band a
    UI would actually threshold at gets almost no boxes. The comparison test
    builds a skewed population and shows v1 puts most of the sample in the
    lowest band while v2 splits it evenly.
    """
    sample: list[dict] = []
    taken: set[str] = set()
    for c in _candidates(store, corridor, population, min_conf, seed):
        if c["image_id"] in taken:
            continue
        c["band"] = band_of(c["conf"])
        sample.append(c)
        taken.add(c["image_id"])
        if len(sample) >= n:
            break
    return sample


def pick_sample(
    store: Store,
    corridor: str,
    *,
    population: str = "perspective",
    n: int = 30,
    min_conf: float = 0.2,
    seed: int = 42,
) -> list[dict]:
    """Stratified sample of animal boxes: equal allocation across BANDS, at most
    one box per frame, deterministic order from a seeded hash. If a band has
    fewer candidates than its share, the shortfall is left unfilled and reported
    rather than back-filled from an easier band."""
    candidates = _candidates(store, corridor, population, min_conf, seed)
    per_band = math.ceil(n / len(BANDS))
    quota = {band_of(lo): per_band for lo, _ in BANDS}
    taken_images: set[str] = set()
    sample: list[dict] = []
    for c in candidates:
        band = band_of(c["conf"])
        if band not in quota or quota[band] == 0 or c["image_id"] in taken_images:
            continue
        c["band"] = band
        sample.append(c)
        quota[band] -= 1
        taken_images.add(c["image_id"])
        if len(sample) >= n:
            break
    short = {b: q for b, q in quota.items() if q > 0}
    if short:
        log.warning("bands short of their quota (not back-filled): %s", short)
    log_filter("review.sample", f"stratified: {per_band} per band over {len(BANDS)} bands, one box per frame, seed {seed}",
               len(candidates), len(sample), corridor=corridor, population=population, min_conf=min_conf,
               by_band={b: sum(1 for x in sample if x["band"] == b) for b, _ in ((band_of(lo), None) for lo, _ in BANDS)}, short=short)
    return sample


def _all_animal_boxes(store: Store, image_id: str, model_version: str, variant: str, min_conf: float) -> list[dict]:
    rows = store.sql(
        """
        SELECT det_idx, conf, bbox_x, bbox_y, bbox_w, bbox_h FROM detections_raw
        WHERE image_id = ? AND model_version = ? AND variant = ? AND category = ? AND conf >= ?
        """,
        [image_id, model_version, variant, ANIMAL_CATEGORY, min_conf],
    )
    return [dict(zip(["det_idx", "conf", "x", "y", "w", "h"], r)) for r in rows]


def source_image_path(row: dict) -> Path:
    """Whole frame: the download itself. Panorama slice: the derived slice file."""
    if row["variant"] == "full":
        return Path(row["local_path"])
    return slice_path_for(Path(row["local_path"]), row["image_id"], row["variant"])


def render_review_images(
    store: Store,
    sample: list[dict],
    out_dir: Path,
    *,
    min_conf: float = 0.2,
    frame_max_px: int = 1600,
    crop_pad: float = 0.75,
) -> None:
    """For each sampled detection write two JPEGs into out_dir:
    <image_id>_<variant>_<det_idx>_frame.jpg  - the whole frame, all animal boxes
                                     drawn, the sampled one in a thicker line
    <image_id>_<variant>_<det_idx>_crop.jpg   - the sampled box with padding,
                                     upscaled, so a 40 px blob is judgeable
    Box coordinates are SpeciesNet's normalised (x_min, y_min, w, h)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for row in sample:
        stem = f"{row['image_id']}_{row['variant']}_{row['det_idx']}"
        with Image.open(source_image_path(row)) as raw:
            # SpeciesNet's loader applies the EXIF orientation tag before running
            # the detector, so its box coordinates refer to the upright image. 13 of
            # the 400 Lamar frames carry a 180-degree tag; without this transpose
            # the boxes would land on the wrong part of the picture.
            im = ImageOps.exif_transpose(raw).convert("RGB")
            W, H = im.size
            boxes = _all_animal_boxes(store, row["image_id"], row["model_version"], row["variant"], min_conf)

            frame = im.copy()
            draw = ImageDraw.Draw(frame)
            for b in boxes:
                x0, y0 = b["x"] * W, b["y"] * H
                x1, y1 = x0 + b["w"] * W, y0 + b["h"] * H
                is_target = b["det_idx"] == row["det_idx"]
                draw.rectangle([x0, y0, x1, y1], outline=(255, 80, 0) if is_target else (255, 220, 0), width=6 if is_target else 3)
                draw.text((x0, max(0, y0 - 14)), f"{b['conf']:.2f}", fill=(255, 255, 255))
            frame.thumbnail((frame_max_px, frame_max_px))
            frame.save(out_dir / f"{stem}_frame.jpg", quality=85)

            # Crop around the sampled box with generous padding for context.
            bx, by, bw, bh = row["bbox_x"] * W, row["bbox_y"] * H, row["bbox_w"] * W, row["bbox_h"] * H
            pad_w, pad_h = max(bw * crop_pad, 64), max(bh * crop_pad, 64)
            box = (int(max(0, bx - pad_w)), int(max(0, by - pad_h)), int(min(W, bx + bw + pad_w)), int(min(H, by + bh + pad_h)))
            crop = im.crop(box)
            if crop.width < 512:  # nearest-neighbour upscale keeps the pixels honest
                scale = 512 / crop.width
                crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.NEAREST)
            crop.save(out_dir / f"{stem}_crop.jpg", quality=90)


def write_review_template(sample: list[dict], path: Path) -> None:
    """Write the CSV I fill in by hand. Never overwrites an existing file, so a
    half-finished review survives re-running the sampler."""
    if path.exists():
        log.warning("%s exists; not overwriting. Delete it to regenerate.", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for row in sample:
            top5 = json.loads(row["top5_classes"] or "[]")
            stem = f"{row['image_id']}_{row['variant']}_{row['det_idx']}"
            writer.writerow(
                {
                    "image_id": row["image_id"],
                    "variant": row["variant"],
                    "det_idx": row["det_idx"],
                    "band": row.get("band", band_of(row["conf"])),
                    "conf": round(row["conf"], 3),
                    "predicted": display_name(row["prediction"]),
                    "prediction_score": round(row["prediction_score"], 3) if row["prediction_score"] is not None else "",
                    "prediction_source": row["prediction_source"],
                    "top5": " | ".join(display_name(c) for c in top5),
                    "source_url": row["source_url"],
                    "frame_file": f"{stem}_frame.jpg",
                    "crop_file": f"{stem}_crop.jpg",
                    "verdict": "", "true_species": "", "species_agree": "", "est_distance_m": "", "notes": "",
                }
            )


def load_review_csv(path: Path, *, reviewer: str = "me") -> list[dict]:
    """Rows from a filled-in review CSV that have a verdict, shaped for
    Store.upsert_reviews. Blank verdict rows are skipped (not yet reviewed)."""
    rows: list[dict] = []
    with open(path, newline="") as fh:
        for rec in csv.DictReader(fh):
            verdict = (rec.get("verdict") or "").strip().lower()
            if not verdict:
                continue
            if verdict not in {"tp", "fp", "unsure"}:
                raise ValueError(f"{path}: bad verdict {verdict!r} for {rec.get('image_id')} (use tp/fp/unsure)")
            dist = (rec.get("est_distance_m") or "").strip()
            rows.append(
                {
                    "image_id": rec["image_id"],
                    "variant": (rec.get("variant") or "full").strip() or "full",
                    "det_idx": int(rec["det_idx"]),
                    "reviewer": reviewer,
                    "verdict": verdict,
                    "true_species": (rec.get("true_species") or "").strip() or None,
                    "species_agree": (rec.get("species_agree") or "").strip().lower() or None,
                    "est_distance_m": float(dist) if dist else None,
                    "notes": (rec.get("notes") or "").strip() or None,
                }
            )
    return rows
