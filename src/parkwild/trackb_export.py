"""The roadside camera pass, summarised per park for the app (E-033).

PROBLEM: the imagery track's counts are tiny next to human sightings, and a
"model 0" badge on every species page raised the question it could not
answer: where did the model run, what did it find, how good was it?

CURRENT: one file per park, one entry per configured corridor in that park,
with the volume (images indexed, frames scored, frames with an animal), the
outcome (sightings, named to species, which species), the imagery's months
and years and contributor count, and the Phase 0 precision with its interval
where a review exists. Corridors with no run yet appear as "planned" so the
map can draw where the pass is queued. Numbers only: no thumbnails, images
are linked by ID elsewhere (ShareAlike caution in the spec).

UNRESOLVED: precision comes from the one reviewer who did the Phase 0 pass;
a second reviewer's numbers are reported separately, never pooled.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .config import Corridor, get_park, load_corridors
from .report import phase0_numbers
from .storage import Store
from .trackb import MIN_CONF, RANGE_M, SPECIES_MIN_SCORE, UNIDENTIFIED_NAME

# MODEL_LINE — DERIVED (what actually ran; the version comes from the runs table when present)
MODEL_LINE = "SpeciesNet {version} (MegaDetector + species classifier), CPU"


def corridor_summary(store: Store, park: str, c: Corridor, *, reviewer: str | None = None) -> dict:
    images = store.one("SELECT count(*) FROM images WHERE corridor = ?", [c.key]) or 0
    frames_scored = store.one(
        "SELECT count(DISTINCT p.image_id) FROM predictions_raw p JOIN images i USING (image_id) WHERE i.corridor = ? AND p.variant = 'full'", [c.key]) or 0
    frames_with_animal = store.one(
        "SELECT count(DISTINCT p.image_id) FROM predictions_raw p JOIN images i USING (image_id) "
        "WHERE i.corridor = ? AND p.variant = 'full' AND p.max_animal_conf >= ?", [c.key, MIN_CONF]) or 0
    rows = store.sql(
        "SELECT scientific_name FROM sightings WHERE source = 'mapillary_cv' AND park = ? AND duplicate_of IS NULL "
        "AND json_extract_string(raw_json, '$.corridor') = ?", [park, c.key])
    named = Counter(r[0] for r in rows if r[0] != UNIDENTIFIED_NAME)
    months = [0] * 12
    for m, n in store.sql("SELECT month(captured_at), count(*) FROM images WHERE corridor = ? AND captured_at IS NOT NULL GROUP BY 1", [c.key]):
        months[int(m) - 1] = n
    years = store.sql("SELECT min(year(captured_at)), max(year(captured_at)) FROM images WHERE corridor = ? AND captured_at IS NOT NULL", [c.key])[0]
    contributors = store.one("SELECT count(DISTINCT creator_username) FROM images WHERE corridor = ?", [c.key]) or 0
    precision = None
    reviewers = [r[0] for r in store.sql(
        "SELECT DISTINCT m.reviewer FROM manual_review m JOIN images i USING (image_id) WHERE i.corridor = ? AND m.variant = 'full'", [c.key])]
    if reviewers:
        who = reviewer if reviewer in reviewers else ("me" if "me" in reviewers else sorted(reviewers)[0])
        rv = phase0_numbers(store, c.key, population="perspective", reviewer=who)["review"]
        precision = {"reviewer": who, "population": "perspective", "n": rv["tp"] + rv["fp"], "tp": rv["tp"],
                     "precision": rv["precision"], "ci": list(rv["precision_ci"]) if rv["precision_ci"] else None,
                     "bands": [{"band": k, "n": v["n"], "tp": v["tp"], "precision": v["precision"], "ci": list(v["ci"]) if v["ci"] else None}
                               for k, v in rv["by_band"].items()]}
    status = "planned" if frames_scored == 0 else ("reviewed" if precision else "unreviewed")
    return {
        "key": c.key, "name": c.name, "bbox": [c.bbox.min_lon, c.bbox.min_lat, c.bbox.max_lon, c.bbox.max_lat], "status": status,
        "images_indexed": images, "frames_scored": frames_scored, "frames_with_animal": frames_with_animal,
        "sightings": len(rows), "named": sum(named.values()), "unnamed": len(rows) - sum(named.values()),
        "species_named": dict(named.most_common()),
        "imagery_years": [int(years[0]), int(years[1])] if years and years[0] is not None else None,
        "imagery_months": months, "contributors": contributors, "precision": precision,
    }


def camera_pass_json(store: Store, park: str, out_path: Path, *, corridors: list[Corridor] | None = None, reviewer: str | None = None) -> dict:
    park_name = get_park(park).name
    cors = corridors if corridors is not None else [c for c in load_corridors().values() if c.park == park_name]
    version = store.one("SELECT speciesnet_version FROM runs WHERE speciesnet_version IS NOT NULL ORDER BY started_at DESC LIMIT 1") or "5.0.5"
    payload = {
        "park": park, "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": MODEL_LINE.format(version=version),
        "thresholds": {"detection_min_conf": MIN_CONF, "species_min_score": SPECIES_MIN_SCORE, "range_m": RANGE_M},
        "corridors": [corridor_summary(store, park, c, reviewer=reviewer) for c in cors],
        "notes": {
            "recall": "unmeasured",
            "precision": "share of reviewed detections a person confirmed as an animal, Wilson 95% interval",
            "attribution": "Mapillary contributors, CC BY-SA 4.0; images linked by ID, never copied",
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, separators=(",", ":")))
    return {"corridors": len(cors), "with_runs": sum(c["status"] != "planned" for c in payload["corridors"])}
