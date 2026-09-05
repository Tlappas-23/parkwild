"""
Build the manual-inspection set for Phase 0.

The brief asks me to look at ~30 detections with my own eyes and say honestly
how many are animals versus rocks, shrubs and logs. This module picks the
sample deterministically, draws the boxes so I can see what the model saw, and
writes a CSV I fill in by hand. The filled CSV is loaded into `manual_review`
by `phase0.py report`.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from PIL import Image, ImageDraw

from .speciesnet_runner import ANIMAL_CATEGORY, display_name
from .storage import Store

log = logging.getLogger(__name__)

REVIEW_COLUMNS = [
    # filled by the script
    "image_id", "det_idx", "conf", "predicted", "prediction_score", "prediction_source",
    "top5", "source_url", "frame_file", "crop_file",
    # filled by me
    "verdict",          # tp | fp | unsure
    "true_species",     # what it actually is (free text; blank if fp)
    "species_agree",    # yes | rollup | no | na   (rollup = model gave a correct coarser taxon)
    "est_distance_m",   # rough range from camera to animal, metres
    "notes",
]


def pick_sample(store: Store, corridor: str, *, n: int = 30, min_conf: float = 0.2, seed: int = 42) -> list[dict]:
    """Random sample of animal detections above `min_conf`, at most one per
    image so 30 rows means 30 different frames. Ordering by a hash of the key
    plus seed is a shuffle that gives the same answer on every machine."""
    rows = store.sql(
        """
        WITH dets AS (
            SELECT d.image_id, d.model_version, d.det_idx, d.conf,
                   d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h,
                   p.prediction, p.prediction_score, p.prediction_source, p.top5_classes,
                   dl.local_path, i.source_url,
                   row_number() OVER (PARTITION BY d.image_id ORDER BY hash(d.image_id || ':' || CAST(d.det_idx AS VARCHAR) || ':' || ?)) AS rn
            FROM detections_raw d
            JOIN predictions_raw p USING (image_id, model_version)
            JOIN downloads dl USING (image_id)
            JOIN images i USING (image_id)
            WHERE i.corridor = ? AND d.category = ? AND d.conf >= ? AND dl.error IS NULL
        )
        SELECT * EXCLUDE (rn) FROM dets WHERE rn = 1
        ORDER BY hash(image_id || ':' || ?)
        LIMIT ?
        """,
        [str(seed), corridor, ANIMAL_CATEGORY, min_conf, str(seed), n],
    )
    keys = [
        "image_id", "model_version", "det_idx", "conf", "bbox_x", "bbox_y", "bbox_w", "bbox_h",
        "prediction", "prediction_score", "prediction_source", "top5_classes", "local_path", "source_url",
    ]
    return [dict(zip(keys, r)) for r in rows]


def _all_animal_boxes(store: Store, image_id: str, model_version: str, min_conf: float) -> list[dict]:
    rows = store.sql(
        """
        SELECT det_idx, conf, bbox_x, bbox_y, bbox_w, bbox_h FROM detections_raw
        WHERE image_id = ? AND model_version = ? AND category = ? AND conf >= ?
        """,
        [image_id, model_version, ANIMAL_CATEGORY, min_conf],
    )
    return [dict(zip(["det_idx", "conf", "x", "y", "w", "h"], r)) for r in rows]


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
    <image_id>_<det_idx>_frame.jpg  - the whole frame, all animal boxes drawn,
                                      the sampled one in a thicker line
    <image_id>_<det_idx>_crop.jpg   - the sampled box with padding, upscaled,
                                      so a 40 px blob is actually judgeable
    The box coordinates are SpeciesNet's normalised (x_min, y_min, w, h)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for row in sample:
        with Image.open(row["local_path"]) as im:
            im = im.convert("RGB")
            W, H = im.size
            boxes = _all_animal_boxes(store, row["image_id"], row["model_version"], min_conf)

            frame = im.copy()
            draw = ImageDraw.Draw(frame)
            for b in boxes:
                x0, y0 = b["x"] * W, b["y"] * H
                x1, y1 = x0 + b["w"] * W, y0 + b["h"] * H
                is_target = b["det_idx"] == row["det_idx"]
                draw.rectangle([x0, y0, x1, y1], outline=(255, 80, 0) if is_target else (255, 220, 0), width=6 if is_target else 3)
                draw.text((x0, max(0, y0 - 14)), f"{b['conf']:.2f}", fill=(255, 255, 255))
            frame.thumbnail((frame_max_px, frame_max_px))
            frame.save(out_dir / f"{row['image_id']}_{row['det_idx']}_frame.jpg", quality=85)

            # Crop around the sampled box with generous padding for context.
            bx, by, bw, bh = row["bbox_x"] * W, row["bbox_y"] * H, row["bbox_w"] * W, row["bbox_h"] * H
            pad_w, pad_h = max(bw * crop_pad, 64), max(bh * crop_pad, 64)
            box = (int(max(0, bx - pad_w)), int(max(0, by - pad_h)), int(min(W, bx + bw + pad_w)), int(min(H, by + bh + pad_h)))
            crop = im.crop(box)
            if crop.width < 512:  # nearest-neighbour upscale keeps the pixels honest
                scale = 512 / crop.width
                crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.NEAREST)
            crop.save(out_dir / f"{row['image_id']}_{row['det_idx']}_crop.jpg", quality=90)


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
            writer.writerow(
                {
                    "image_id": row["image_id"],
                    "det_idx": row["det_idx"],
                    "conf": round(row["conf"], 3),
                    "predicted": display_name(row["prediction"]),
                    "prediction_score": round(row["prediction_score"], 3) if row["prediction_score"] is not None else "",
                    "prediction_source": row["prediction_source"],
                    "top5": " | ".join(display_name(c) for c in top5),
                    "source_url": row["source_url"],
                    "frame_file": f"{row['image_id']}_{row['det_idx']}_frame.jpg",
                    "crop_file": f"{row['image_id']}_{row['det_idx']}_crop.jpg",
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
