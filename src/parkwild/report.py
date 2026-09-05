"""
Compute the Phase 0 numbers and write them into RESULTS.md.

The brief wants five things: detection rate, true-positive rate on manual
inspection, distance at which detection works, species agreement, and image
density / date range. Everything here is a SQL query over the raw tables plus
the manual_review table; nothing is hand-edited.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .speciesnet_runner import ANIMAL_CATEGORY, HUMAN_CATEGORY, VEHICLE_CATEGORY, display_name
from .storage import Store

THRESHOLDS = (0.2, 0.5, 0.8)


def phase0_numbers(
    store: Store,
    corridor: str,
    *,
    det_threshold: float = 0.2,
    road_km: float | None = None,
    trail_km: float | None = None,
) -> dict:
    n: dict = {"corridor": corridor, "det_threshold": det_threshold, "road_km": road_km, "trail_km": trail_km}

    # ---- volume ---------------------------------------------------------------
    n["n_indexed"] = store.count_images(corridor)
    n["n_downloaded"] = store.one(
        "SELECT count(*) FROM downloads d JOIN images i USING (image_id) WHERE i.corridor = ? AND d.error IS NULL", [corridor]
    )
    n["n_download_failed"] = store.one(
        "SELECT count(*) FROM downloads d JOIN images i USING (image_id) WHERE i.corridor = ? AND d.error IS NOT NULL", [corridor]
    )
    n["n_predicted"] = store.one(
        "SELECT count(*) FROM predictions_raw p JOIN images i USING (image_id) WHERE i.corridor = ?", [corridor]
    )
    n["n_model_failures"] = store.one(
        "SELECT count(*) FROM predictions_raw p JOIN images i USING (image_id) WHERE i.corridor = ? AND p.failures IS NOT NULL", [corridor]
    )
    n["model_versions"] = [r[0] for r in store.sql(
        "SELECT DISTINCT p.model_version FROM predictions_raw p JOIN images i USING (image_id) WHERE i.corridor = ?", [corridor]
    )]

    # ---- number 1: fraction of images with an animal detection ----------------
    n["images_with_animal"] = {}
    for t in sorted(set(THRESHOLDS) | {det_threshold}):
        count = store.one(
            "SELECT count(*) FROM predictions_raw p JOIN images i USING (image_id) WHERE i.corridor = ? AND p.max_animal_conf >= ?",
            [corridor, t],
        )
        n["images_with_animal"][t] = {"count": count, "frac": (count / n["n_predicted"]) if n["n_predicted"] else None}
    for name, cat in (("human", HUMAN_CATEGORY), ("vehicle", VEHICLE_CATEGORY)):
        n[f"images_with_{name}"] = store.one(
            """SELECT count(DISTINCT d.image_id) FROM detections_raw d JOIN images i USING (image_id)
               WHERE i.corridor = ? AND d.category = ? AND d.conf >= ?""",
            [corridor, cat, det_threshold],
        )
    n["ensemble_labels"] = [
        (display_name(lbl), cnt)
        for lbl, cnt in store.sql(
            """SELECT p.prediction, count(*) AS c FROM predictions_raw p JOIN images i USING (image_id)
               WHERE i.corridor = ? AND p.max_animal_conf >= ? GROUP BY p.prediction ORDER BY c DESC LIMIT 12""",
            [corridor, det_threshold],
        )
    ]
    n["prediction_sources"] = store.sql(
        """SELECT p.prediction_source, count(*) AS c FROM predictions_raw p JOIN images i USING (image_id)
           WHERE i.corridor = ? GROUP BY 1 ORDER BY c DESC""",
        [corridor],
    )

    # ---- numbers 2-4: manual review ------------------------------------------
    rev = store.sql(
        """SELECT m.verdict, m.species_agree, m.est_distance_m FROM manual_review m
           JOIN images i USING (image_id) WHERE i.corridor = ?""",
        [corridor],
    )
    verdicts = [r[0] for r in rev]
    tp = sum(v == "tp" for v in verdicts)
    fp = sum(v == "fp" for v in verdicts)
    unsure = sum(v == "unsure" for v in verdicts)
    n["review"] = {
        "n_reviewed": len(rev), "tp": tp, "fp": fp, "unsure": unsure,
        "precision": (tp / (tp + fp)) if (tp + fp) else None,
    }
    tp_dists = sorted(r[2] for r in rev if r[0] == "tp" and r[2] is not None)
    n["review"]["distances_m"] = {
        "n": len(tp_dists),
        "median": _percentile(tp_dists, 50),
        "p90": _percentile(tp_dists, 90),
        "max": tp_dists[-1] if tp_dists else None,
    }
    agree = [(r[1] or "na") for r in rev if r[0] == "tp"]
    n["review"]["species"] = {
        "n_tp_with_label": sum(a != "na" for a in agree),
        "exact": sum(a == "yes" for a in agree),
        "rollup": sum(a == "rollup" for a in agree),
        "wrong": sum(a == "no" for a in agree),
    }

    # ---- number 5: density and dates ----------------------------------------
    stats = store.sql(
        """SELECT min(captured_at), max(captured_at), count(DISTINCT sequence_id), count(DISTINCT creator_username),
                  sum(CASE WHEN is_pano THEN 1 ELSE 0 END)
           FROM images WHERE corridor = ?""",
        [corridor],
    )[0]
    n["date_min"], n["date_max"], n["n_sequences"], n["n_contributors"], n["n_pano"] = stats
    n["images_per_year"] = store.sql(
        "SELECT year(captured_at) AS y, count(*) FROM images WHERE corridor = ? GROUP BY y ORDER BY y", [corridor]
    )
    n["images_per_month"] = store.sql(
        "SELECT month(captured_at) AS m, count(*) FROM images WHERE corridor = ? GROUP BY m ORDER BY m", [corridor]
    )
    n["camera_types"] = store.sql(
        "SELECT coalesce(camera_type, 'unknown'), count(*) AS c FROM images WHERE corridor = ? GROUP BY 1 ORDER BY c DESC", [corridor]
    )
    n["images_per_road_km"] = (n["n_indexed"] / road_km) if road_km else None
    return n


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _num(x: float | None, unit: str = "") -> str:
    return "n/a" if x is None else f"{x:,.0f}{unit}"


def render_phase0_markdown(n: dict) -> str:
    """Markdown block for RESULTS.md. Written so that a reader who only sees this
    block still knows whether the idea works."""
    t = n["det_threshold"]
    r = n["review"]
    lines = [
        f"_Generated {datetime.now():%Y-%m-%d %H:%M} from `data/parkwild.duckdb`. Model versions: {', '.join(n['model_versions']) or 'none yet'}._",
        "",
        "**Volume**",
        "",
        f"| Indexed | Downloaded | Download failed | Run through SpeciesNet | Model failures |",
        f"|---|---|---|---|---|",
        f"| {n['n_indexed']:,} | {n['n_downloaded']:,} | {n['n_download_failed']:,} | {n['n_predicted']:,} | {n['n_model_failures']:,} |",
        "",
        f"**1. Images with any MegaDetector animal detection**",
        "",
        "| Threshold | Images | Fraction |",
        "|---|---|---|",
    ]
    for thr, v in sorted(n["images_with_animal"].items()):
        lines.append(f"| >= {thr} | {v['count']:,} | {_pct(v['frac'])} |")
    lines += [
        "",
        f"For context at >= {t}: {n['images_with_human']:,} images have a human box and {n['images_with_vehicle']:,} a vehicle box.",
        "",
        f"Top ensemble labels on images with an animal box >= {t}: "
        + (", ".join(f"{lbl} ({cnt})" for lbl, cnt in n["ensemble_labels"]) or "none"),
        "",
        f"**2. True positives on manual inspection** ({r['n_reviewed']} boxes reviewed)",
        "",
        f"- true positive: {r['tp']}, false positive: {r['fp']}, unsure: {r['unsure']}",
        f"- precision (tp / (tp + fp)): {_pct(r['precision'])}",
        "",
        f"**3. Distance of true positives from the camera** (n={r['distances_m']['n']} with an estimate)",
        "",
        f"- median {_num(r['distances_m']['median'], ' m')}, p90 {_num(r['distances_m']['p90'], ' m')}, farthest confirmed {_num(r['distances_m']['max'], ' m')}",
        "",
        f"**4. Species agreement on true positives** ({r['species']['n_tp_with_label']} judged)",
        "",
        f"- exact: {r['species']['exact']}, correct coarser taxon (rollup): {r['species']['rollup']}, wrong: {r['species']['wrong']}",
        "",
        "**5. Mapillary density in the corridor**",
        "",
        f"- {n['n_indexed']:,} images in {n['n_sequences'] or 0:,} sequences from {n['n_contributors'] or 0:,} contributors; {n['n_pano'] or 0:,} panoramas",
        f"- road inside bbox (OSM): {_num(n['road_km'], ' km')}; trail: {_num(n['trail_km'], ' km')}; images per road km: {_num(n['images_per_road_km'])}",
        f"- captured between {n['date_min']} and {n['date_max']}",
        f"- by year: " + (", ".join(f"{int(y)}: {c:,}" for y, c in n["images_per_year"] if y is not None) or "n/a"),
        f"- by month: " + (", ".join(f"{int(m)}: {c:,}" for m, c in n["images_per_month"] if m is not None) or "n/a"),
        f"- camera types: " + ", ".join(f"{ct}: {c:,}" for ct, c in n["camera_types"]),
        "",
    ]
    return "\n".join(lines)


def update_results_md(path: Path, corridor: str, block: str) -> None:
    """Replace the auto-generated block for this corridor between HTML-comment
    markers, or append a new section if the markers aren't there yet. Everything
    outside the markers is mine to edit by hand and is left alone."""
    start, end = f"<!-- phase0:{corridor}:start -->", f"<!-- phase0:{corridor}:end -->"
    text = path.read_text() if path.exists() else "# RESULTS\n"
    replacement = f"{start}\n{block}\n{end}"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(lambda _: replacement, text)
    else:
        text = text.rstrip("\n") + f"\n\n### Phase 0 numbers: {corridor}\n\n{replacement}\n"
    path.write_text(text)


def dump_json(n: dict) -> str:
    return json.dumps(n, indent=2, default=str)
