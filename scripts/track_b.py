#!/usr/bin/env python
"""
Track B driver beyond Phase 0: detections into the sightings schema.

    track_b.py sightings --corridor lamar_valley --park yellowstone [--population perspective] [--min-conf 0.5]

Runs after `phase0.py detect`. Idempotent: rows are keyed by image, slice and box.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parkwild.config import get_corridor, get_park  # noqa: E402
from parkwild.decisionlog import print_decision_summary  # noqa: E402
from parkwild.storage import Store  # noqa: E402
from parkwild.trackb import MIN_CONF, detections_to_sightings  # noqa: E402


def cmd_sightings(args):
    corridor = get_corridor(args.corridor)
    park = get_park(args.park)
    with Store() as store:
        r = detections_to_sightings(store, corridor.key, park.key, population=args.population, min_conf=args.min_conf)
    print(json.dumps(r))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sightings", help="write model-predicted sightings for a corridor")
    p.add_argument("--corridor", required=True)
    p.add_argument("--park", required=True)
    p.add_argument("--population", choices=["perspective", "pano"], default="perspective")
    p.add_argument("--min-conf", type=float, default=MIN_CONF)
    p.set_defaults(func=cmd_sightings)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    args.func(args)
    print_decision_summary()


if __name__ == "__main__":
    main()
