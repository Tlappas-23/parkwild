"""Track B into the sightings schema, at supplementary scope (ADR-0013/0014).

PROBLEM: the app reads one `sightings` table. Detections live in the raw
prediction tables, one row per box, twenty rows per roadside bison, with a
camera position rather than an animal position and species labels the
Phase 0 review showed to be no better than "large mammal" here.

CURRENT: for one corridor, take animal boxes at or above MIN_CONF whose
ensemble label is not human, vehicle or blank; chain consecutive frames the
way report.cluster_detections does and keep one sighting per chain (the
frame with the strongest box); position it at that camera with the measured
detection range as the stated accuracy; name the species only when the
classifier is confident, otherwise "Mammalia" with a plain "unidentified
large mammal (model)" common name; carry the Mapillary image ID, contributor
and licence on every row. Everything is `confidence_basis='model_predicted'`
and the app draws it differently.

CONSIDERED, NOT DONE: projecting the animal's position along the compass
bearing by the estimated range (Phase 4). The bearing is stored in raw_json
for when that lands; until then the camera cell is the honest cell, and at
H3 r9 (~170 m) it is usually the right one for a bison at 45 to 150 m.

UNRESOLVED: precision of this layer is the Phase 0 figure (42% at 0.2, about
two thirds at 0.5 after the human filter, n tiny). The About page says so.
"""
from __future__ import annotations

import json
import logging

from .decisionlog import log_filter
from .geo import haversine_m
from .report import CLUSTER_DIST_M, CLUSTER_GAP_S
from .speciesnet_runner import ANIMAL_CATEGORY, split_label
from .storage import VARIANT_FILTER, Store

log = logging.getLogger(__name__)

# MIN_CONF — MEASURED (2026-09-05, Lamar perspective review, reviewer claude)
#
# Precision by detector band, boxes with an ensemble label of human/vehicle removed:
#     0.2 to 0.5   3 tp / 6 fp   (n=9)    people on motorcycles labelled "unknown", trees, a car, a road
#     0.5 to 0.8   4 tp / 2 fp   (n=6)    the two fp are lone conifers at 0.53 and 0.74
#     0.8+         1 tp / 0 fp   (n=1)
# 0.5 keeps the band where a box is more often an animal than not. n is tiny;
# the interval on 4/6 runs from 30% to 90%.
# REVISIT IF: the owner's review pass or a larger sample moves the band curve.
MIN_CONF = 0.5

# EXCLUDED_LABELS — MEASURED (same review)
# Six of eleven perspective false positives were people the ensemble labelled
# "human"; the model already knows. "vehicle" is removed too, at the cost of two
# reviewed bison the ensemble mislabelled as vehicles at 0.20 and 0.55.
# "blank" means the classifier saw nothing; the box is kept only if the detector
# alone is strong, which is what MIN_CONF already tests, so blank is excluded.
EXCLUDED_LABELS = ("human", "vehicle", "blank")

# SPECIES_MIN_SCORE — ASSUMED
# Name the species only when the classifier's own score is at least this; below
# it the row is "unidentified large mammal". In the review the classifier named
# 5 of 8 bison correctly and called two of them vehicles, so confidence in the
# label is warranted only near the top.
SPECIES_MIN_SCORE = 0.8

# RANGE_M — MEASURED (2026-09-05, Lamar perspective review)
# Farthest confirmed true positive: 150 m; median 70 m. Stored as the
# positional accuracy of a model-predicted sighting placed at the camera.
RANGE_M = 150.0

# UNIDENTIFIED_NAME / UNIDENTIFIED_COMMON — ASSUMED
# The class is the deepest rank the Phase 0 review supports for an unnamed box
# (every reviewed true positive was a large mammal). The common name says
# "model" so the label is never mistaken for a person's identification.
UNIDENTIFIED_NAME = "Mammalia"
UNIDENTIFIED_COMMON = "unidentified large mammal (model)"


def _species_from_label(label: str | None, score: float | None) -> tuple[str, str | None, str | None]:
    """(scientific_name, common_name, rank) for a sighting row."""
    parts = split_label(label)
    if "raw" not in parts and parts["species"] and (score or 0) >= SPECIES_MIN_SCORE:
        genus, species = parts["genus"], parts["species"]
        sci = f"{genus.capitalize()} {species}"
        return sci, parts["common_name"] or None, "species"
    return UNIDENTIFIED_NAME, UNIDENTIFIED_COMMON, "class"


def detections_to_sightings(
    store: Store,
    corridor: str,
    park: str,
    *,
    population: str = "perspective",
    min_conf: float = MIN_CONF,
    gap_s: float = CLUSTER_GAP_S,
    dist_m: float = CLUSTER_DIST_M,
) -> dict:
    """Upsert one model-predicted sighting per frame-chain of qualifying boxes."""
    rows = store.sql(
        f"""
        SELECT d.image_id, d.variant, d.det_idx, d.conf, d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h,
               p.prediction, p.prediction_score, p.model_version,
               i.sequence_id, i.captured_at_ms, i.captured_at, i.lon, i.lat,
               coalesce(i.computed_compass_angle, i.compass_angle) AS bearing,
               i.creator_username, i.license, i.source_url, i.width, i.height
        FROM detections_raw d
        JOIN predictions_raw p USING (image_id, model_version, variant)
        JOIN images i USING (image_id)
        WHERE i.corridor = ? AND d.category = ? AND d.{VARIANT_FILTER[population]}
        ORDER BY i.sequence_id, i.captured_at_ms, d.image_id, d.conf DESC
        """,
        [corridor, ANIMAL_CATEGORY],
    )
    n_boxes = len(rows)
    kept = []
    dropped_conf = dropped_label = 0
    for r in rows:
        if r[3] < min_conf:
            dropped_conf += 1
            continue
        parts = split_label(r[8])
        label_name = parts.get("raw") or parts.get("common_name") or ""
        if label_name in EXCLUDED_LABELS:
            dropped_label += 1
            continue
        kept.append(r)
    log_filter("track_b.sightings.filter", f"animal boxes with conf >= {min_conf} and ensemble label not in {EXCLUDED_LABELS}",
               n_boxes, len(kept), corridor=corridor, population=population, dropped_conf=dropped_conf, dropped_label=dropped_label)

    # One sighting per frame-chain: same sequence, same *resolved* species,
    # consecutive frames within gap/dist. Resolving first means a bison whose
    # label flickers between low-confidence guesses still folds into one
    # "unidentified" chain, while a confidently named bison and an unnamed box
    # in the next frame stay two sightings. Chains are keyed per species so
    # interleaved frames of two animals do not break each other's chain.
    chains: list[list[tuple]] = []
    open_chain: dict[tuple, dict] = {}
    for r in kept:
        seq, ts, lon, lat = r[11], r[12], r[14], r[15]
        sci, _, _ = _species_from_label(r[8], r[9])
        key = (seq, sci)
        last = open_chain.get(key)
        same = (
            last is not None
            and ts is not None and last["ts"] is not None and abs(ts - last["ts"]) <= gap_s * 1000
            and None not in (lon, lat, last["lon"], last["lat"])
            and haversine_m(lon, lat, last["lon"], last["lat"]) <= dist_m
        )
        if same:
            chains[last["idx"]].append(r)
            last.update(ts=ts, lon=lon, lat=lat)
        else:
            chains.append([r])
            open_chain[key] = {"ts": ts, "lon": lon, "lat": lat, "idx": len(chains) - 1}
    log_filter("track_b.sightings.chains", f"one sighting per frame-chain (same sequence and resolved species, within {gap_s:.0f} s and {dist_m:.0f} m)",
               len(kept), len(chains), corridor=corridor, population=population)

    sightings = []
    for chain in chains:
        best = max(chain, key=lambda r: r[3])
        (image_id, variant, det_idx, conf, bx, by, bw, bh, label, score, model_version,
         seq, ts, captured_at, lon, lat, bearing, user, lic, url, w, h) = best
        sci, common, rank = _species_from_label(label, score)
        sightings.append({
            "sighting_id": f"mapillary_cv:{image_id}:{variant}:{det_idx}",
            "source": "mapillary_cv",
            "source_id": f"{image_id}:{variant}:{det_idx}",
            "dataset": model_version,
            "park": park,
            "confidence_basis": "model_predicted",
            "taxon_id": None,
            "scientific_name": sci,
            "common_name": common,
            "taxon_rank": rank,
            "taxon_class": "Mammalia",
            "observed_at": captured_at,
            "observed_on": captured_at.date().isoformat() if captured_at else None,
            "lon": lon,
            "lat": lat,
            "positional_accuracy_m": RANGE_M,
            "coordinate_status": "open" if lon is not None else "missing",
            "observer": user,
            "license": lic,
            "url": url,
            "attribution": f"{user} via Mapillary, {lic}, {url}; detection by SpeciesNet {model_version}",
            "duplicate_of": None,
            "raw_json": json.dumps({
                "corridor": corridor, "population": population, "image_id": image_id, "variant": variant, "det_idx": det_idx,
                "detector_conf": conf, "bbox": [bx, by, bw, bh], "ensemble_label": label, "ensemble_score": score,
                "camera_bearing_deg": bearing, "frame_width": w, "frame_height": h,
                "chain_frames": len(chain), "chain_image_ids": [c[0] for c in chain],
                "range_m_assumed": RANGE_M, "position": "camera; bearing stored for Phase 4 projection",
            }, separators=(",", ":"), default=str),
        })
    # Derived rows, not raw output: clear this corridor's previous model-predicted
    # sightings first, so a rule change never leaves a stale row behind (a
    # "domestic cattle" row outlived the NOT_WILD rule on the first rerun).
    store.con.execute(
        "DELETE FROM sightings WHERE source = 'mapillary_cv' AND park = ? AND json_extract_string(raw_json, '$.corridor') = ?",
        [park, corridor],
    )
    n_written = store.upsert_sightings(sightings)
    named = sum(1 for s in sightings if s["taxon_rank"] == "species")
    return {"boxes": n_boxes, "kept_boxes": len(kept), "chains": len(chains), "written": n_written, "named_species": named}
