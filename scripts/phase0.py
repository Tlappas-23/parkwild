#!/usr/bin/env python
"""
Phase 0 driver: the feasibility gate.

Run the subcommands in order. Each is idempotent and resumable, so re-running
after an interruption picks up where it stopped instead of starting over.

    phase0.py coverage                              # what Mapillary has in each candidate corridor
    phase0.py pull     --corridor lamar_valley      # index every image in the corridor into DuckDB
    phase0.py download --corridor lamar_valley      # fetch ~400 full-resolution frames
    phase0.py detect   --corridor lamar_valley      # MegaDetector + SpeciesNet; store raw output
    phase0.py sample   --corridor lamar_valley      # gallery + CSV for the ~30-box manual review
    phase0.py report   --corridor lamar_valley --write   # the five numbers -> RESULTS.md

Then stop and decide whether to proceed to Phase 1.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Works without `pip install -e .` too, by putting src/ on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parkwild.config import (  # noqa: E402
    DATA_DIR, IMAGES_DIR, PREDICTIONS_DIR, RESULTS_MD, REVIEW_DIR,
    get_corridor, load_corridors, mapillary_token,
)
from parkwild.download import download_images  # noqa: E402
from parkwild.geo import DEFAULT_TILE_DEG  # noqa: E402
from parkwild.mapillary import (  # noqa: E402
    COVERAGE_FIELDS, IMAGE_FIELDS, MAPILLARY_DETECTIONS_FIELD, MapillaryClient, flatten_image,
)
from parkwild.overpass import fetch_highways, summarize_length_km  # noqa: E402
from parkwild.report import dump_json, phase0_numbers, render_phase0_markdown, update_results_md  # noqa: E402
from parkwild.review import load_review_csv, pick_sample, render_review_images, write_review_template  # noqa: E402
from parkwild.speciesnet_runner import parse_predictions, run_speciesnet  # noqa: E402
from parkwild.storage import Store  # noqa: E402

log = logging.getLogger("phase0")


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
        fmt = lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
        summary[key] = {
            "name": c.name,
            "bbox": c.bbox.as_mapillary(),
            "bbox_km": [round(ew_km, 1), round(ns_km, 1)],
            "images": len(ids),
            "sequences": len(seqs),
            "first": fmt(min(times)) if times else None,
            "last": fmt(max(times)) if times else None,
            "tiles_queried": n_tiles,
            "tiles_truncated": n_capped,
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
    record, upsert by image ID, and mark the tile done so a rerun skips it."""
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
            store.upsert_images(rows)
            store.upsert_tile(c.key, res.tile, res.status, len(rows))
            total += len(rows)
            log.info("tile %s: %d images (%s)", res.tile.tile_id, len(rows), res.status)
        print(f"{c.key}: {total:,} records fetched this run; {store.count_images(c.key):,} images indexed in total")


# ---- download ------------------------------------------------------------------

def cmd_download(args: argparse.Namespace) -> None:
    """Fetch pixels for a spread sample of indexed images. Panoramas are skipped by
    default: the detector was not trained on equirectangular projections."""
    c = get_corridor(args.corridor)
    client = MapillaryClient(mapillary_token())
    with Store() as store:
        summary = download_images(
            store, client, c.key,
            out_dir=IMAGES_DIR / c.key,
            size=args.size,
            limit=args.limit,
            max_per_sequence=args.max_per_sequence,
            exclude_pano=not args.include_pano,
            workers=args.workers,
        )
    print(summary)


# ---- detect --------------------------------------------------------------------

def cmd_detect(args: argparse.Namespace) -> None:
    """Run the SpeciesNet ensemble over the corridor's image folder, then parse
    its JSON into predictions_raw / detections_raw. --parse-only skips the model
    (useful after running SpeciesNet elsewhere, e.g. on Kaggle, and copying the
    JSON into data/predictions/)."""
    c = get_corridor(args.corridor)
    image_dir = IMAGES_DIR / c.key
    predictions_json = PREDICTIONS_DIR / f"{c.key}.json"
    if not args.parse_only:
        if not image_dir.exists() or not any(image_dir.glob("*.jpg")):
            sys.exit(f"no images in {image_dir}; run `download` first")
        code = run_speciesnet(
            image_dir, predictions_json,
            country="USA",
            admin1_region=None if args.no_admin1 else c.state,
            batch_size=args.batch_size,
            python=args.python,
        )
        if code != 0:
            sys.exit(f"speciesnet exited with {code}")
    if not predictions_json.exists():
        sys.exit(f"{predictions_json} not found")
    run_id = f"{c.key}:{datetime.fromtimestamp(predictions_json.stat().st_mtime):%Y%m%dT%H%M%S}"
    preds, dets = parse_predictions(predictions_json, run_id=run_id)
    with Store() as store:
        store.upsert_predictions(preds)
        store.upsert_detections(dets)
    n_animal = sum(1 for p in preds if (p["max_animal_conf"] or 0) >= 0.2)
    print(f"{len(preds)} predictions, {len(dets)} boxes stored; {n_animal} images with an animal box >= 0.2")


# ---- sample --------------------------------------------------------------------

def cmd_sample(args: argparse.Namespace) -> None:
    """Build the manual-review set: pick ~30 animal boxes, render frame + crop
    images, and write data/review/<corridor>/review.csv for me to fill in."""
    c = get_corridor(args.corridor)
    out_dir = REVIEW_DIR / c.key
    with Store() as store:
        sample = pick_sample(store, c.key, n=args.n, min_conf=args.min_conf, seed=args.seed)
        if not sample:
            print("no animal detections at or above the threshold; nothing to review (that is itself a result)")
            return
        render_review_images(store, sample, out_dir, min_conf=args.min_conf)
        write_review_template(sample, out_dir / "review.csv")
    print(f"{len(sample)} boxes rendered into {out_dir}")
    print(f"fill in verdict / true_species / species_agree / est_distance_m in {out_dir / 'review.csv'},")
    print("or open notebooks/phase0_inspection.ipynb, then run `phase0.py report`.")


# ---- report --------------------------------------------------------------------

def cmd_report(args: argparse.Namespace) -> None:
    """Import any filled review CSV, measure road length via Overpass, compute the
    five Phase 0 numbers, print them, and optionally write them into RESULTS.md."""
    c = get_corridor(args.corridor)
    review_csv = REVIEW_DIR / c.key / "review.csv"
    road_km = trail_km = None
    if not args.no_overpass:
        try:
            ways = fetch_highways(c.bbox)
            lengths = summarize_length_km(ways, c.bbox)
            road_km, trail_km = lengths["road_km"], lengths["trail_km"]
            log.info("OSM inside bbox: %s", lengths)
        except Exception as exc:  # density is nice to have; don't fail the report over it
            log.warning("Overpass failed (%s); density will be n/a", exc)
    with Store() as store:
        if review_csv.exists():
            rows = load_review_csv(review_csv, reviewer=args.reviewer)
            store.upsert_reviews(rows)
            log.info("imported %d verdicts from %s", len(rows), review_csv)
        numbers = phase0_numbers(store, c.key, det_threshold=args.threshold, road_km=road_km, trail_km=trail_km)
    block = render_phase0_markdown(numbers)
    print(block)
    if args.json:
        out = DATA_DIR / f"phase0_{c.key}.json"
        out.write_text(dump_json(numbers))
        print(f"wrote {out}")
    if args.write:
        update_results_md(RESULTS_MD, c.key, block)
        print(f"updated {RESULTS_MD}")


# ---- argparse ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

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
    p.add_argument("--limit", type=int, default=400, help="how many images to fetch this run")
    p.add_argument("--max-per-sequence", type=int, default=20, help="spread the sample across sequences")
    p.add_argument("--size", choices=["original", "2048", "1024"], default="original")
    p.add_argument("--include-pano", action="store_true")
    p.add_argument("--workers", type=int, default=4)
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("detect", help="run MegaDetector + SpeciesNet and store raw output")
    p.add_argument("--corridor", required=True)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--python", default=sys.executable, help="interpreter that has speciesnet installed")
    p.add_argument("--no-admin1", action="store_true", help="geofence to USA only, not the corridor's state")
    p.add_argument("--parse-only", action="store_true", help="skip inference; just load an existing predictions JSON")
    p.set_defaults(func=cmd_detect)

    p = sub.add_parser("sample", help="build the manual review gallery and CSV")
    p.add_argument("--corridor", required=True)
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--min-conf", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("report", help="compute the Phase 0 numbers")
    p.add_argument("--corridor", required=True)
    p.add_argument("--threshold", type=float, default=0.2)
    p.add_argument("--reviewer", default="me")
    p.add_argument("--no-overpass", action="store_true", help="skip the OSM road-length query")
    p.add_argument("--json", action="store_true", help="also dump the numbers to data/phase0_<corridor>.json")
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


if __name__ == "__main__":
    main()
