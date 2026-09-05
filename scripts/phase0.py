#!/usr/bin/env python
"""
Phase 0 driver: the feasibility gate, now a router (BUILD_SPEC.md).

Two populations are measured separately: whole perspective frames, and
panoramas sliced into horizon windows. Every subcommand takes --population.
Each step is idempotent and resumable.

    phase0.py coverage                                     # what Mapillary has in each corridor
    phase0.py pull     --corridor lamar_valley             # index every image into DuckDB
    phase0.py download --corridor lamar_valley [--population pano --limit 100]
    phase0.py slice    --corridor lamar_valley             # panoramas -> 4 yaw windows each
    phase0.py detect   --corridor lamar_valley --population perspective|pano
    phase0.py sample   --corridor lamar_valley --population ...   # stratified 30-box review set
    phase0.py report   --corridor lamar_valley --population ... --write

Then route on the numbers (DECISIONS.md), don't halt.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Works without `pip install -e .` too, by putting src/ on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parkwild.config import (  # noqa: E402
    DATA_DIR,
    IMAGES_DIR,
    PREDICTIONS_DIR,
    RESULTS_MD,
    REVIEW_DIR,
    get_corridor,
    load_corridors,
    mapillary_token,
)
from parkwild.contracts import check_lon_lat, check_ms_epoch  # noqa: E402
from parkwild.decisionlog import log_filter, print_decision_summary, record_sample  # noqa: E402
from parkwild.download import download_images  # noqa: E402
from parkwild.geo import DEFAULT_TILE_DEG  # noqa: E402
from parkwild.mapillary import (  # noqa: E402
    COVERAGE_FIELDS,
    IMAGE_FIELDS,
    MAPILLARY_DETECTIONS_FIELD,
    MapillaryClient,
    flatten_image,
)
from parkwild.overpass import fetch_highways, summarize_length_km  # noqa: E402
from parkwild.pano import slice_all, slices_dir_for  # noqa: E402
from parkwild.report import dump_json, phase0_numbers, render_phase0_markdown, update_results_md  # noqa: E402
from parkwild.review import load_review_csv, pick_sample, render_review_images, write_review_template  # noqa: E402
from parkwild.speciesnet_runner import parse_predictions, run_speciesnet, speciesnet_env_info  # noqa: E402
from parkwild.storage import Store  # noqa: E402

log = logging.getLogger("phase0")
# POPULATIONS — BORROWED (ADR-0006: the two populations measured separately)
POPULATIONS = ("perspective", "pano")


def image_dir_for(corridor: str, population: str) -> Path:
    """Where each population's pixels live. Panorama *slices* are what the
    detector reads; the whole panoramas sit next to them."""
    if population == "perspective":
        return IMAGES_DIR / corridor
    return IMAGES_DIR / f"{corridor}_pano"


def detect_dir_for(corridor: str, population: str) -> Path:
    base = image_dir_for(corridor, population)
    return base if population == "perspective" else slices_dir_for(base)


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


# ---- coverage ---------------------------------------------------------------

def cmd_coverage(args: argparse.Namespace) -> None:
    """Count images, sequences and the date range in each candidate corridor
    using the cheapest field set. Doesn't write to the database; the point is to
    pick a corridor, not to index one. Saves a JSON summary for the record."""
    client = MapillaryClient(mapillary_token())
    corridors = load_corridors()
    keys = [args.corridor] if args.corridor else list(corridors)
    summary: dict[str, dict] = {}
    for key in keys:
        c = corridors[key]
        ids: set[str] = set()
        seqs: set[str] = set()
        times: list[int] = []
        n_tiles = n_capped = 0
        for res in client.crawl(c.bbox, fields=COVERAGE_FIELDS, tile_deg=args.tile_deg):
            n_tiles += 1
            n_capped += int(res.hit_cap and not res.split)
            for rec in res.records:
                ids.add(rec["id"])
                if rec.get("sequence"):
                    seqs.add(rec["sequence"])
                if rec.get("captured_at"):
                    times.append(rec["captured_at"])
        ew_km, ns_km = c.bbox.approx_size_km()
        fmt = lambda ms: datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")  # noqa: E731
        summary[key] = {
            "name": c.name, "bbox": c.bbox.as_mapillary(), "bbox_km": [round(ew_km, 1), round(ns_km, 1)],
            "images": len(ids), "sequences": len(seqs),
            "first": fmt(min(times)) if times else None, "last": fmt(max(times)) if times else None,
            "tiles_queried": n_tiles, "tiles_truncated": n_capped,
        }
        s = summary[key]
        print(f"{key:14s} {s['images']:>7,} images  {s['sequences']:>5,} sequences  {s['first']} .. {s['last']}"
              f"  ({n_tiles} tiles, {n_capped} truncated)  {c.name}")
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / f"coverage_{datetime.now():%Y%m%d}.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {out}")


# ---- pull ----------------------------------------------------------------------

def cmd_pull(args: argparse.Namespace) -> None:
    """Index every image in the corridor bbox: crawl tile by tile, flatten each
    record, contract-check it, upsert by image ID, and mark the tile done so a
    rerun skips it."""
    c = get_corridor(args.corridor)
    fields = list(IMAGE_FIELDS)
    if args.with_mapillary_detections:
        fields.append(MAPILLARY_DETECTIONS_FIELD)
    client = MapillaryClient(mapillary_token())
    with Store() as store:
        if args.fresh:
            store.clear_tiles(c.key)
        skip = store.done_tile_ids(c.key)
        if skip:
            log.info("resuming: %d tiles already done", len(skip))
        total = 0
        for res in client.crawl(c.bbox, fields=fields, tile_deg=args.tile_deg, skip_tile_ids=skip):
            rows = [flatten_image(rec, c.key) for rec in res.records]
            check_lon_lat(rows)
            check_ms_epoch(r["captured_at_ms"] for r in rows)
            store.upsert_images(rows)
            store.upsert_tile(c.key, res.tile, res.status, len(rows))
            total += len(rows)
            log.info("tile %s: %d images (%s)", res.tile.tile_id, len(rows), res.status)
        n_total = store.count_images(c.key)
    log_filter("phase0.pull", "records fetched vs distinct image ids stored (tile overlap dedupes)", total, n_total, corridor=c.key)
    print(f"{c.key}: {total:,} records fetched this run; {n_total:,} images indexed in total")


# ---- download ------------------------------------------------------------------

def cmd_download(args: argparse.Namespace) -> None:
    """Fetch pixels for a spread sample of one population."""
    c = get_corridor(args.corridor)
    client = MapillaryClient(mapillary_token())
    with Store() as store:
        n_pop = store.one(
            "SELECT count(*) FROM images WHERE corridor = ? AND coalesce(is_pano,false) = ?", [c.key, args.population == "pano"]
        )
        summary = download_images(
            store, client, c.key,
            out_dir=image_dir_for(c.key, args.population),
            size=args.size, limit=args.limit, max_per_sequence=args.max_per_sequence,
            population=args.population, workers=args.workers,
        )
    log_filter("phase0.download", f"{args.population}: spread sample, max {args.max_per_sequence} per sequence",
               n_pop, summary["ok"], corridor=c.key, requested=summary["requested"], failed=summary["failed"])
    print(summary)


# ---- slice ---------------------------------------------------------------------

def cmd_slice(args: argparse.Namespace) -> None:
    """Cut every downloaded panorama into four 90-degree horizon windows. This
    fixes projection and framing for the detector; it does not add resolution."""
    c = get_corridor(args.corridor)
    with Store() as store:
        panos = store.downloaded(c.key, population="pano")
    if not panos:
        sys.exit("no panoramas downloaded; run `download --population pano` first")
    out_dir = slices_dir_for(image_dir_for(c.key, "pano"))
    summary = slice_all(panos, out_dir, hfov_deg=args.hfov, vfov_deg=args.vfov)
    log_filter("phase0.slice", f"{args.hfov:.0f} deg yaw windows x 4, {args.vfov:.0f} deg pitch band", summary["panos"], summary["slices"], corridor=c.key)
    print(f"{summary['panos']} panoramas -> {summary['slices']} slices in {out_dir}")


# ---- detect --------------------------------------------------------------------

def cmd_detect(args: argparse.Namespace) -> None:
    """Run the SpeciesNet ensemble over one population's image folder, record
    the run (backend included), then parse its JSON into the append-only raw
    tables. --backend external skips the model for JSON produced elsewhere."""
    c = get_corridor(args.corridor)
    image_dir = detect_dir_for(c.key, args.population)
    predictions_json = PREDICTIONS_DIR / f"{c.key}_{args.population}.json"
    files = sorted(image_dir.glob("*.jpg")) if image_dir.exists() else []
    run_id = f"{c.key}:{args.population}:{datetime.now():%Y%m%dT%H%M%S}"
    started = _utcnow()
    exit_code = None
    # Backend is recorded per run (build spec, Phase 2). 'cpu' is the measured
    # default on this machine: MPS segfaults in SpeciesNet's classifier
    # preprocessing past a handful of frames (E-012). 'external' means the JSON
    # was produced elsewhere (Kaggle) and is only parsed here.
    env = {"speciesnet_version": "external", "backend": "external"}
    if args.backend != "external":
        if not files:
            sys.exit(f"no images in {image_dir}; run `download` (and `slice` for panoramas) first")
        env = speciesnet_env_info(args.python)
        if args.backend == "cpu":
            env["backend"] = "cpu"
        exit_code = run_speciesnet(
            image_dir, predictions_json, country="USA",
            admin1_region=None if args.no_admin1 else c.state,
            batch_size=args.batch_size, python=args.python, force_cpu=(args.backend == "cpu"),
        )
    if not predictions_json.exists():
        sys.exit(f"{predictions_json} not found")
    preds, dets = parse_predictions(predictions_json, run_id=run_id)
    with Store() as store:
        model_versions = sorted({p["model_version"] for p in preds})
        store.record_run({
            "run_id": run_id, "corridor": c.key, "population": args.population,
            "model_version": ",".join(model_versions), "speciesnet_version": env["speciesnet_version"], "backend": env["backend"],
            "image_dir": str(image_dir), "predictions_json": str(predictions_json), "n_files": len(files),
            "country": "USA", "admin1_region": None if args.no_admin1 else c.state, "batch_size": args.batch_size,
            "exit_code": exit_code, "started_at": started, "finished_at": _utcnow(),
            "notes": "parsed external JSON" if args.backend == "external" else None,
        })
        new_p = store.append_predictions(preds)
        new_d = store.append_detections(dets)
    if exit_code not in (None, 0):
        sys.exit(f"speciesnet exited with {exit_code}; parsed what it wrote")
    log_filter("phase0.detect", "predictions parsed vs newly stored (append-only; existing rows untouched)",
               len(preds), new_p, corridor=c.key, population=args.population, run_id=run_id, boxes_parsed=len(dets), boxes_new=new_d)
    n_animal = sum(1 for p in preds if (p["max_animal_conf"] or 0) >= 0.2)
    print(f"{len(preds)} predictions ({new_p} new), {len(dets)} boxes ({new_d} new); {n_animal} frames/slices with an animal box >= 0.2")


# ---- sample --------------------------------------------------------------------

def cmd_sample(args: argparse.Namespace) -> None:
    """Build the manual-review set for one population: a stratified sample of
    animal boxes, rendered frames and crops, and review.csv to fill in."""
    c = get_corridor(args.corridor)
    out_dir = REVIEW_DIR / c.key / args.population
    with Store() as store:
        sample = pick_sample(store, c.key, population=args.population, n=args.n, min_conf=args.min_conf, seed=args.seed)
        if not sample:
            print("no animal detections at or above the threshold; nothing to review (that is itself a result)")
            return
        render_review_images(store, sample, out_dir, min_conf=args.min_conf)
        write_review_template(sample, out_dir / "review.csv")
    record_sample(f"{c.key}_{args.population}_review", [f"{x['image_id']}:{x['variant']}:{x['det_idx']}" for x in sample],
                  seed=args.seed, n=args.n, min_conf=args.min_conf)
    bands = {}
    for s in sample:
        bands[s["band"]] = bands.get(s["band"], 0) + 1
    print(f"{len(sample)} boxes rendered into {out_dir}; by band: {bands}")
    print(f"fill in verdict / true_species / species_agree / est_distance_m in {out_dir / 'review.csv'},")
    print("or open notebooks/phase0_inspection.ipynb, then run `phase0.py report`.")


# ---- report --------------------------------------------------------------------

def cmd_report(args: argparse.Namespace) -> None:
    """Import any filled review CSV, measure road length via Overpass, compute
    the Phase 0 numbers for one population, print them, optionally write them."""
    c = get_corridor(args.corridor)
    review_csv = REVIEW_DIR / c.key / args.population / "review.csv"
    road_km = trail_km = None
    if not args.no_overpass:
        try:
            lengths = summarize_length_km(fetch_highways(c.bbox), c.bbox)
            road_km, trail_km = lengths["road_km"], lengths["trail_km"]
            log.info("OSM inside bbox: %s", lengths)
        except Exception as exc:
            log.warning("Overpass failed (%s); density will be n/a", exc)
    with Store() as store:
        if review_csv.exists():
            rows = load_review_csv(review_csv, reviewer=args.reviewer)
            store.upsert_reviews(rows)
            log.info("imported %d verdicts from %s", len(rows), review_csv)
        numbers = phase0_numbers(store, c.key, population=args.population, det_threshold=args.threshold, road_km=road_km, trail_km=trail_km)
    block = render_phase0_markdown(numbers)
    print(block)
    key = f"{c.key}:{args.population}"
    if args.json:
        out = DATA_DIR / f"phase0_{c.key}_{args.population}.json"
        out.write_text(dump_json(numbers))
        print(f"wrote {out}")
    if args.write:
        update_results_md(RESULTS_MD, key, block)
        print(f"updated {RESULTS_MD} block {key}")


# ---- argparse ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    def pop_arg(p):
        p.add_argument("--population", choices=POPULATIONS, default="perspective")

    p = sub.add_parser("coverage", help="count Mapillary images in each candidate corridor")
    p.add_argument("--corridor", help="restrict to one corridor key")
    p.add_argument("--tile-deg", type=float, default=DEFAULT_TILE_DEG)
    p.set_defaults(func=cmd_coverage)

    p = sub.add_parser("pull", help="index all images in a corridor into DuckDB")
    p.add_argument("--corridor", required=True)
    p.add_argument("--tile-deg", type=float, default=DEFAULT_TILE_DEG)
    p.add_argument("--fresh", action="store_true", help="ignore tile progress and re-crawl everything")
    p.add_argument("--with-mapillary-detections", action="store_true",
                   help="also fetch Mapillary's own segmentation labels (detections.value) per image")
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("download", help="download a sample of full-resolution images")
    p.add_argument("--corridor", required=True)
    pop_arg(p)
    p.add_argument("--limit", type=int, default=400, help="how many images to fetch this run")
    p.add_argument("--max-per-sequence", type=int, default=20, help="spread the sample across sequences")
    p.add_argument("--size", choices=["original", "2048", "1024"], default="original")
    p.add_argument("--workers", type=int, default=4)
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("slice", help="cut downloaded panoramas into horizon windows")
    p.add_argument("--corridor", required=True)
    p.add_argument("--hfov", type=float, default=90.0)
    p.add_argument("--vfov", type=float, default=60.0)
    p.set_defaults(func=cmd_slice)

    p = sub.add_parser("detect", help="run MegaDetector + SpeciesNet and store raw output")
    p.add_argument("--corridor", required=True)
    pop_arg(p)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--python", default=sys.executable, help="interpreter that has speciesnet installed")
    p.add_argument("--no-admin1", action="store_true", help="geofence to USA only, not the corridor's state")
    p.add_argument("--backend", choices=["cpu", "auto", "external"], default="cpu",
                   help="cpu (measured default, E-012) | auto (let torch pick; MPS crashes here) | external (parse a JSON made elsewhere)")
    p.set_defaults(func=cmd_detect)

    p = sub.add_parser("sample", help="build the manual review gallery and CSV")
    p.add_argument("--corridor", required=True)
    pop_arg(p)
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--min-conf", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("report", help="compute the Phase 0 numbers")
    p.add_argument("--corridor", required=True)
    pop_arg(p)
    p.add_argument("--threshold", type=float, default=0.2)
    p.add_argument("--reviewer", default="me")
    p.add_argument("--no-overpass", action="store_true", help="skip the OSM road-length query")
    p.add_argument("--json", action="store_true", help="also dump the numbers to data/phase0_<corridor>_<population>.json")
    p.add_argument("--write", action="store_true", help="write the block into RESULTS.md")
    p.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    args.func(args)
    print_decision_summary()


if __name__ == "__main__":
    main()
