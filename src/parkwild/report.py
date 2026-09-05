"""
Compute the Phase 0 numbers and write them into RESULTS.md.

The brief wants five things: detection rate, true-positive rate on manual
inspection, distance at which detection works, species agreement, and image
density / date range. The build spec adds: report per population, precision
with a confidence interval, a distinct-cluster count next to the raw box count,
and never a recall figure. Everything here is a SQL query over the raw tables
plus the manual_review table; nothing is hand-edited.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

from .geo import haversine_m
from .speciesnet_runner import ANIMAL_CATEGORY, HUMAN_CATEGORY, VEHICLE_CATEGORY, display_name
from .storage import POPULATION_FILTER, VARIANT_FILTER, Store

THRESHOLDS = (0.2, 0.5, 0.8)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion k/n. Better than the normal
    approximation at the small n this project actually has."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def cluster_detections(
    store: Store,
    corridor: str,
    *,
    population: str = "perspective",
    min_conf: float = 0.2,
    gap_s: float = 60.0,
    dist_m: float = 200.0,
) -> dict:
    """Group animal boxes that are probably the same animals seen from
    consecutive frames.

    A cluster is a chain of *frames* in one sequence with the same ensemble
    label, each within `gap_s` seconds and `dist_m` metres of the previous
    frame in the chain. Boxes inside one frame are never merged: two elk in a
    frame are two elk. The estimated number of distinct individuals is the sum
    over clusters of the largest per-frame box count in that cluster. For
    panorama slices the "frame" is the panorama, so slices of one panorama
    count together.
    """
    rows = store.sql(
        f"""
        SELECT d.image_id, i.sequence_id, i.captured_at_ms, i.lon, i.lat, p.prediction, count(*) AS n_boxes
        FROM detections_raw d
        JOIN predictions_raw p USING (image_id, model_version, variant)
        JOIN images i USING (image_id)
        WHERE i.corridor = ? AND d.category = ? AND d.conf >= ? AND d.{VARIANT_FILTER[population]}
        GROUP BY d.image_id, i.sequence_id, i.captured_at_ms, i.lon, i.lat, p.prediction
        ORDER BY i.sequence_id, i.captured_at_ms, d.image_id, p.prediction
        """,
        [corridor, ANIMAL_CATEGORY, min_conf],
    )
    n_boxes = sum(r[6] for r in rows)
    images = {r[0] for r in rows}
    # One open chain per (sequence, label): the last frame seen for it.
    open_chains: dict[tuple, dict] = {}
    clusters: list[int] = []   # max boxes per frame within each closed/open chain
    for image_id, seq, ts, lon, lat, label, nb in rows:
        key = (seq, label)
        last = open_chains.get(key)
        same = (
            last is not None
            and ts is not None and last["ts"] is not None and abs(ts - last["ts"]) <= gap_s * 1000
            and None not in (lon, lat, last["lon"], last["lat"])
            and haversine_m(lon, lat, last["lon"], last["lat"]) <= dist_m
        )
        if same:
            last.update(ts=ts, lon=lon, lat=lat)
            clusters[last["idx"]] = max(clusters[last["idx"]], nb)
        else:
            clusters.append(nb)
            open_chains[key] = {"ts": ts, "lon": lon, "lat": lat, "idx": len(clusters) - 1}
    n_clusters = len(clusters)
    n_individuals = sum(clusters)
    return {
        "n_boxes": n_boxes,
        "n_images": len(images),
        "n_clusters": n_clusters,
        "n_individuals_est": n_individuals,
        "duplicate_rate": (1 - n_individuals / n_boxes) if n_boxes else None,
        "gap_s": gap_s,
        "dist_m": dist_m,
    }


def phase0_numbers(
    store: Store,
    corridor: str,
    *,
    population: str = "perspective",
    det_threshold: float = 0.2,
    road_km: float | None = None,
    trail_km: float | None = None,
) -> dict:
    if population not in VARIANT_FILTER:
        raise ValueError(f"population must be one of {list(VARIANT_FILTER)}")
    vf = VARIANT_FILTER[population]
    pf = POPULATION_FILTER[population]
    n: dict = {
        "corridor": corridor, "population": population, "det_threshold": det_threshold,
        "road_km": road_km, "trail_km": trail_km, "recall": "unmeasured",
    }

    # ---- volume ---------------------------------------------------------------
    n["n_indexed_all"] = store.count_images(corridor)
    n["n_indexed"] = store.one(f"SELECT count(*) FROM images WHERE corridor = ? AND {pf}", [corridor])
    n["n_downloaded"] = store.one(
        f"SELECT count(*) FROM downloads d JOIN images i USING (image_id) WHERE i.corridor = ? AND d.error IS NULL AND {pf}", [corridor]
    )
    n["n_download_failed"] = store.one(
        f"SELECT count(*) FROM downloads d JOIN images i USING (image_id) WHERE i.corridor = ? AND d.error IS NOT NULL AND {pf}", [corridor]
    )
    # For panoramas an "image" is the panorama; its slices are variants of it.
    n["n_predicted"] = store.one(
        f"SELECT count(DISTINCT p.image_id) FROM predictions_raw p JOIN images i USING (image_id) WHERE i.corridor = ? AND p.{vf}", [corridor]
    )
    n["n_variants_predicted"] = store.one(
        f"SELECT count(*) FROM predictions_raw p JOIN images i USING (image_id) WHERE i.corridor = ? AND p.{vf}", [corridor]
    )
    n["n_model_failures"] = store.one(
        f"SELECT count(*) FROM predictions_raw p JOIN images i USING (image_id) WHERE i.corridor = ? AND p.{vf} AND p.failures IS NOT NULL", [corridor]
    )
    n["model_versions"] = [r[0] for r in store.sql(
        f"SELECT DISTINCT p.model_version FROM predictions_raw p JOIN images i USING (image_id) WHERE i.corridor = ? AND p.{vf}", [corridor]
    )]

    # ---- number 1: fraction of images with an animal detection ----------------
    n["images_with_animal"] = {}
    for t in sorted(set(THRESHOLDS) | {det_threshold}):
        count = store.one(
            f"SELECT count(DISTINCT p.image_id) FROM predictions_raw p JOIN images i USING (image_id) "
            f"WHERE i.corridor = ? AND p.{vf} AND p.max_animal_conf >= ?",
            [corridor, t],
        )
        frac = (count / n["n_predicted"]) if n["n_predicted"] else None
        n["images_with_animal"][t] = {"count": count, "frac": frac, "ci": wilson(count, n["n_predicted"]) if n["n_predicted"] else None}
    for name, cat in (("human", HUMAN_CATEGORY), ("vehicle", VEHICLE_CATEGORY)):
        n[f"images_with_{name}"] = store.one(
            f"""SELECT count(DISTINCT d.image_id) FROM detections_raw d JOIN images i USING (image_id)
               WHERE i.corridor = ? AND d.category = ? AND d.conf >= ? AND d.{vf}""",
            [corridor, cat, det_threshold],
        )
    n["ensemble_labels"] = [
        (display_name(lbl), cnt)
        for lbl, cnt in store.sql(
            f"""SELECT p.prediction, count(*) AS c FROM predictions_raw p JOIN images i USING (image_id)
               WHERE i.corridor = ? AND p.{vf} AND p.max_animal_conf >= ? GROUP BY p.prediction ORDER BY c DESC LIMIT 12""",
            [corridor, det_threshold],
        )
    ]
    n["clusters"] = cluster_detections(store, corridor, population=population, min_conf=det_threshold)

    # ---- numbers 2-4: manual review ------------------------------------------
    rev = store.sql(
        f"""SELECT m.verdict, m.species_agree, m.est_distance_m, d.conf FROM manual_review m
           JOIN detections_raw d USING (image_id, variant, det_idx)
           JOIN images i USING (image_id) WHERE i.corridor = ? AND m.{vf}""",
        [corridor],
    )
    verdicts = [r[0] for r in rev]
    tp = sum(v == "tp" for v in verdicts)
    fp = sum(v == "fp" for v in verdicts)
    unsure = sum(v == "unsure" for v in verdicts)
    n["review"] = {
        "n_reviewed": len(rev), "tp": tp, "fp": fp, "unsure": unsure,
        "precision": (tp / (tp + fp)) if (tp + fp) else None,
        "precision_ci": wilson(tp, tp + fp) if (tp + fp) else None,
        "by_band": {},
    }
    for lo, hi in ((0.2, 0.5), (0.5, 0.8), (0.8, 1.01)):
        band = [r for r in rev if r[3] is not None and lo <= r[3] < hi]
        btp = sum(r[0] == "tp" for r in band)
        bfp = sum(r[0] == "fp" for r in band)
        n["review"]["by_band"][f"{lo:.1f}-{min(hi, 1.0):.1f}"] = {
            "n": len(band), "tp": btp, "fp": bfp,
            "precision": (btp / (btp + bfp)) if (btp + bfp) else None,
            "ci": wilson(btp, btp + bfp) if (btp + bfp) else None,
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

    # ---- number 5: density and dates (whole corridor, then this population) --
    stats = store.sql(
        """SELECT min(captured_at), max(captured_at), count(DISTINCT sequence_id), count(DISTINCT creator_username),
                  sum(CASE WHEN is_pano THEN 1 ELSE 0 END)
           FROM images WHERE corridor = ?""",
        [corridor],
    )[0]
    n["date_min"], n["date_max"], n["n_sequences"], n["n_contributors"], n["n_pano"] = stats
    n["images_per_year"] = store.sql(
        f"SELECT year(captured_at) AS y, count(*) FROM images WHERE corridor = ? AND {pf} GROUP BY y ORDER BY y", [corridor]
    )
    n["images_per_month"] = store.sql(
        f"SELECT month(captured_at) AS m, count(*) FROM images WHERE corridor = ? AND {pf} GROUP BY m ORDER BY m", [corridor]
    )
    n["camera_types"] = store.sql(
        "SELECT coalesce(camera_type, 'unknown'), count(*) AS c FROM images WHERE corridor = ? GROUP BY 1 ORDER BY c DESC", [corridor]
    )
    n["images_per_road_km"] = (n["n_indexed_all"] / road_km) if road_km else None
    return n


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _ci(ci: tuple[float, float] | None) -> str:
    return "" if ci is None else f" (95% CI {100 * ci[0]:.0f} to {100 * ci[1]:.0f}%)"


def _num(x: float | None, unit: str = "") -> str:
    return "n/a" if x is None else f"{x:,.0f}{unit}"


def render_phase0_markdown(n: dict) -> str:
    """Markdown block for RESULTS.md. Written so that a reader who only sees this
    block still knows whether the idea works."""
    t = n["det_threshold"]
    r = n["review"]
    c = n["clusters"]
    pop = n["population"]
    lines = [
        f"_Population: **{pop}**. Generated {datetime.now():%Y-%m-%d %H:%M} from `data/parkwild.duckdb`. "
        f"Model versions: {', '.join(n['model_versions']) or 'none yet'}. Recall: **{n['recall']}**._",
        "",
        "**Volume**",
        "",
        "| Indexed (this population) | Downloaded | Download failed | Run through SpeciesNet | Frames/slices scored | Model failures |",
        "|---|---|---|---|---|---|",
        f"| {n['n_indexed']:,} | {n['n_downloaded']:,} | {n['n_download_failed']:,} | {n['n_predicted']:,} "
        f"| {n['n_variants_predicted']:,} | {n['n_model_failures']:,} |",
        "",
        "**1. Images with any MegaDetector animal detection**",
        "",
        "| Threshold | Images | Fraction |",
        "|---|---|---|",
    ]
    for thr, v in sorted(n["images_with_animal"].items()):
        lines.append(f"| >= {thr} | {v['count']:,} | {_pct(v['frac'])}{_ci(v['ci'])} |")
    lines += [
        "",
        f"At >= {t}: {c['n_boxes']:,} animal boxes in {c['n_images']:,} images form {c['n_clusters']:,} frame-chains "
        f"(same sequence, same label, consecutive frames within {c['gap_s']:.0f} s and {c['dist_m']:.0f} m), "
        f"an estimated {c['n_individuals_est']:,} distinct individuals; duplicate rate {_pct(c['duplicate_rate'])}.",
        f"For context at >= {t}: {n['images_with_human']:,} images have a human box and {n['images_with_vehicle']:,} a vehicle box.",
        "",
        f"Top ensemble labels on images with an animal box >= {t}: "
        + (", ".join(f"{lbl} ({cnt})" for lbl, cnt in n["ensemble_labels"]) or "none"),
        "",
        f"**2. True positives on manual inspection** ({r['n_reviewed']} boxes reviewed, stratified by confidence band)",
        "",
        f"- true positive: {r['tp']}, false positive: {r['fp']}, unsure: {r['unsure']}",
        f"- precision (tp / (tp + fp)): {_pct(r['precision'])}{_ci(r['precision_ci'])}",
    ]
    for band, b in r["by_band"].items():
        lines.append(f"- band {band}: n={b['n']}, precision {_pct(b['precision'])}{_ci(b['ci'])}")
    lines += [
        "- recall: unmeasured (no exhaustive annotation exists; a number would be invented)",
        "",
        f"**3. Distance of true positives from the camera** (n={r['distances_m']['n']} with an estimate)",
        "",
        f"- median {_num(r['distances_m']['median'], ' m')}, p90 {_num(r['distances_m']['p90'], ' m')}, "
        f"farthest confirmed {_num(r['distances_m']['max'], ' m')}",
        "",
        f"**4. Species agreement on true positives** ({r['species']['n_tp_with_label']} judged)",
        "",
        f"- exact: {r['species']['exact']}, correct coarser taxon (rollup): {r['species']['rollup']}, wrong: {r['species']['wrong']}",
        "",
        "**5. Mapillary density in the corridor** (whole corridor, both populations)",
        "",
        f"- {n['n_indexed_all']:,} images in {n['n_sequences'] or 0:,} sequences from {n['n_contributors'] or 0:,} contributors; "
        f"{n['n_pano'] or 0:,} panoramas",
        f"- road inside bbox (OSM): {_num(n['road_km'], ' km')}; trail: {_num(n['trail_km'], ' km')}; images per road km: {_num(n['images_per_road_km'])}",
        f"- captured between {n['date_min']} and {n['date_max']}",
        "- this population by year: " + (", ".join(f"{int(y)}: {cnt:,}" for y, cnt in n["images_per_year"] if y is not None) or "n/a"),
        "- this population by month: " + (", ".join(f"{int(m)}: {cnt:,}" for m, cnt in n["images_per_month"] if m is not None) or "n/a"),
        "- camera types: " + ", ".join(f"{ct}: {cnt:,}" for ct, cnt in n["camera_types"]),
        "",
    ]
    return "\n".join(lines)


def update_results_md(path: Path, key: str, block: str) -> None:
    """Replace the auto-generated block for `key` (e.g. 'lamar_valley:perspective')
    between HTML-comment markers, or append a new section if the markers aren't
    there yet. Everything outside the markers is hand-written and left alone."""
    start, end = f"<!-- phase0:{key}:start -->", f"<!-- phase0:{key}:end -->"
    text = path.read_text() if path.exists() else "# RESULTS\n"
    replacement = f"{start}\n{block}\n{end}"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(lambda _: replacement, text)
    else:
        text = text.rstrip("\n") + f"\n\n### Phase 0 numbers: {key}\n\n{replacement}\n"
    path.write_text(text)


def dump_json(n: dict) -> str:
    return json.dumps(n, indent=2, default=str)
