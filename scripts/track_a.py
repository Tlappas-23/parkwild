#!/usr/bin/env python
"""
Track A driver: reference sightings from iNaturalist and GBIF.

    track_a.py places  --query "Yellowstone National Park"   # find an iNat place id
    track_a.py ingest  --park yellowstone [--source inaturalist|gbif|all] [--classes Mammalia,Aves]
    track_a.py dedupe  --park yellowstone
    track_a.py export  --park yellowstone      # data/export/<park>/{cells.geojson,species.json,sightings.parquet,manifest.json}
    track_a.py summary --park yellowstone
    track_a.py landmarks --park yellowstone   # boundary.geojson + landmarks.json for the tour
    track_a.py roads     --park yellowstone   # roads.json: OSM roads + trails graph for directions
    track_a.py amenities --park yellowstone   # amenities.json: things to do, camping, trails
    track_a.py index                          # app/public/data/parks.json for the home page (all parks)
    track_a.py all     --park yellowstone      # ingest all + dedupe + export

Every step is idempotent: re-running refreshes the mirror and re-derives the
duplicates and exports.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parkwild import gbif  # noqa: E402
from parkwild.amenities import build_amenities  # noqa: E402
from parkwild.bias import render_bias_markdown, road_bias, seasonal_bias  # noqa: E402
from parkwild.config import EXPORT_DIR, RESULTS_MD, get_corridor, get_park  # noqa: E402
from parkwild.decisionlog import print_decision_summary  # noqa: E402
from parkwild.export import export_park  # noqa: E402
from parkwild.inaturalist import find_places  # noqa: E402
from parkwild.landmarks import build_landmarks  # noqa: E402
from parkwild.parksindex import build_index  # noqa: E402
from parkwild.report import update_results_md  # noqa: E402
from parkwild.roads import build_roads  # noqa: E402
from parkwild.sightings import dedupe, ingest_gbif, ingest_inaturalist, park_summary  # noqa: E402
from parkwild.storage import Store  # noqa: E402

log = logging.getLogger("track_a")


def cmd_places(args):
    for p in find_places(args.query):
        print(json.dumps(p))


def cmd_ingest(args):
    park = get_park(args.park)
    classes = tuple(c.strip() for c in args.classes.split(","))
    with Store() as store:
        if args.source in ("inaturalist", "all"):
            r = ingest_inaturalist(store, park.key, place_id=park.inat_place_id, bbox=None, max_records=args.max_records)
            print("inaturalist:", json.dumps(r))
        if args.source in ("gbif", "all"):
            if args.gbif_counts_only:
                for cls in classes:
                    key = gbif.CLASS_KEYS[cls]
                    print(f"gbif {cls}: total={gbif.count(park.bbox, key):,}")
                    for ds, n in gbif.count_by_dataset(park.bbox, key):
                        tag = " (iNaturalist mirror)" if ds == gbif.INAT_DATASET_KEY else (" (eBird)" if ds == gbif.EBIRD_DATASET_KEY else "")
                        print(f"    {n:>8,}  {ds}{tag}")
                return
            skip = (gbif.INAT_DATASET_KEY,) if args.include_ebird else (gbif.INAT_DATASET_KEY, gbif.EBIRD_DATASET_KEY)
            r = ingest_gbif(store, park.key, park.bbox, classes=classes, max_records=args.max_records, skip_datasets=skip)
            print("gbif:", json.dumps(r))


def cmd_dedupe(args):
    park = get_park(args.park)
    with Store() as store:
        print(json.dumps(dedupe(store, park.key)))


def cmd_export(args):
    park = get_park(args.park)
    out_dir = EXPORT_DIR / park.key
    with Store() as store:
        print(json.dumps(export_park(store, park.key, out_dir)))
    print(f"wrote {out_dir}")


def cmd_summary(args):
    park = get_park(args.park)
    with Store(read_only=True) as store:
        print(json.dumps(park_summary(store, park.key), indent=2, default=str))


def cmd_bias(args):
    """Road and seasonal bias of one corridor's imagery against the park's
    independent sightings. --write puts the block into RESULTS.md."""
    park = get_park(args.park)
    corridor = get_corridor(args.corridor)
    with Store() as store:
        road = road_bias(store, park.key, corridor.key, corridor.bbox, ring=args.ring)
        season = seasonal_bias(store, park.key, corridor.key)
    block = render_bias_markdown(road, season)
    print(block)
    if args.write:
        update_results_md(RESULTS_MD, f"bias:{corridor.key}", block, heading=f"### Bias: {corridor.key}")
        out = EXPORT_DIR / park.key / "bias.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"road": road, "seasonal": season}, indent=1, default=str))
        print(f"updated {RESULTS_MD}; wrote {out} (re-run `export` to refresh the manifest)")


def cmd_landmarks(args):
    """Boundary + landmarks + tour stops for one park (network: iNaturalist,
    Overpass, Wikipedia; no database). Rehashes the manifest afterwards."""
    park = get_park(args.park)
    print(json.dumps(build_landmarks(park, EXPORT_DIR / park.key, summaries=not args.no_summaries), indent=2))


def cmd_roads(args):
    """Roads and trails inside the park bbox as a routing graph (network:
    Overpass; no database). Rehashes the manifest afterwards."""
    park = get_park(args.park)
    print(json.dumps(build_roads(park, EXPORT_DIR / park.key), indent=2))


def cmd_index(args):
    """parks.json for the home page: every configured park, counts for the
    exported ones, a credited hero photograph (network: Wikipedia, Commons)."""
    print(json.dumps(build_index(heroes=not args.no_heroes), indent=2))


def cmd_amenities(args):
    """Things to do around the park's places: OSM campsites, lodging,
    trailheads, viewpoints, picnic sites, visitor centres, boat launches,
    named features, and named trails from roads.json (network, no database)."""
    park = get_park(args.park)
    print(json.dumps(build_amenities(park, EXPORT_DIR / park.key), indent=2))


def cmd_all(args):
    args.source = "all"
    args.gbif_counts_only = False
    args.include_ebird = getattr(args, "include_ebird", False)
    cmd_ingest(args)
    cmd_dedupe(args)
    cmd_export(args)
    cmd_summary(args)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("places", help="look up iNaturalist place ids")
    p.add_argument("--query", required=True)
    p.set_defaults(func=cmd_places)

    p = sub.add_parser("ingest", help="pull sightings into DuckDB")
    p.add_argument("--park", required=True)
    p.add_argument("--source", choices=["inaturalist", "gbif", "all"], default="all")
    p.add_argument("--classes", default="Mammalia,Aves", help="GBIF classes to pull (iNaturalist always gets both)")
    p.add_argument("--max-records", type=int, default=None, help="cap per source/class, for trial runs")
    p.add_argument("--gbif-counts-only", action="store_true", help="print GBIF counts by dataset and exit")
    p.add_argument("--include-ebird", action="store_true",
                   help="also pull eBird checklists from GBIF (421,940 records for Yellowstone; off until decided, ADR-0011)")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("dedupe", help="mark cross-source duplicates")
    p.add_argument("--park", required=True)
    p.set_defaults(func=cmd_dedupe)

    p = sub.add_parser("export", help="bake cells.geojson, species.json, sightings.parquet, manifest.json")
    p.add_argument("--park", required=True)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("summary", help="counts by source, class, coordinate status")
    p.add_argument("--park", required=True)
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("bias", help="road and seasonal bias of a corridor's imagery vs park sightings")
    p.add_argument("--park", required=True)
    p.add_argument("--corridor", required=True)
    p.add_argument("--ring", type=int, default=1, help="H3 r9 rings around an image cell that count as covered")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_bias)

    p = sub.add_parser("landmarks", help="park boundary, OSM landmarks and the curated tour (network, no database)")
    p.add_argument("--park", required=True)
    p.add_argument("--no-summaries", action="store_true", help="skip the Wikipedia excerpts")
    p.set_defaults(func=cmd_landmarks)

    p = sub.add_parser("roads", help="OSM roads and trails as a routing graph for the app (network, no database)")
    p.add_argument("--park", required=True)
    p.set_defaults(func=cmd_roads)

    p = sub.add_parser("amenities", help="amenities.json: things to do, camping, trails around the park's places (network, no database)")
    p.add_argument("--park", required=True)
    p.set_defaults(func=cmd_amenities)

    p = sub.add_parser("index", help="app/public/data/parks.json: every park, counts, credited hero image (network, no database)")
    p.add_argument("--no-heroes", action="store_true")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("all", help="ingest all sources, dedupe, export, summarise")
    p.add_argument("--park", required=True)
    p.add_argument("--classes", default="Mammalia,Aves")
    p.add_argument("--max-records", type=int, default=None)
    p.add_argument("--include-ebird", action="store_true")
    p.set_defaults(func=cmd_all)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    args.func(args)
    print_decision_summary()


if __name__ == "__main__":
    main()
