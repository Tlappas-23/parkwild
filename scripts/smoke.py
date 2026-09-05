#!/usr/bin/env python
"""
Smoke test: the full pipeline path on fixtures, no network, one command.
CI caps it at 5 minutes; locally it runs in a few seconds.

Exercises: crawl-record flattening -> DuckDB -> SpeciesNet JSON parse ->
stratified review sample -> Phase 0 numbers, and Track A normalisation ->
dedupe -> export with manifest verification. Exits non-zero on any mismatch.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from conftest import gbif_occurrences, inat_observations, seed_phase0  # noqa: E402

from parkwild import gbif, inaturalist  # noqa: E402
from parkwild.export import export_park  # noqa: E402
from parkwild.mapillary import flatten_image  # noqa: E402
from parkwild.report import phase0_numbers, render_phase0_markdown  # noqa: E402
from parkwild.review import pick_sample  # noqa: E402
from parkwild.sightings import dedupe  # noqa: E402
from parkwild.storage import Store  # noqa: E402


def check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"SMOKE FAIL: {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"ok  {msg}")


def main() -> None:
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with Store(tmp / "smoke.duckdb") as store:
            # Track B path on fixtures
            rec = {"id": "42", "computed_geometry": {"type": "Point", "coordinates": [-110.2, 44.9]}, "captured_at": 1_700_000_000_000,
                   "creator": {"id": "1", "username": "alice"}, "sequence": "s", "is_pano": False, "camera_type": "perspective"}
            row = flatten_image(rec, "test")
            check(row["lat"] == 44.9 and row["lon"] == -110.2 and row["license"] == "CC BY-SA 4.0", "flatten_image keeps lon/lat order and attribution")
            seed_phase0(store, tmp)
            check(store.count("predictions_raw") == 6, "SpeciesNet JSON parsed into append-only tables")
            sample = pick_sample(store, "test", n=30)
            check(len(sample) == 3 and len({s["image_id"] for s in sample}) == 3, "stratified sample, one box per frame")
            n = phase0_numbers(store, "test", road_km=10.0)
            md = render_phase0_markdown(n)
            check("recall: unmeasured" in md and "95% CI" in md, "Phase 0 report states CI and no recall")

            # Track A path on fixtures
            store.upsert_sightings([inaturalist.normalize(o, "yellowstone") for o in inat_observations()])
            store.upsert_sightings([gbif.normalize(o, "yellowstone") for o in gbif_occurrences() if o["datasetKey"] != gbif.INAT_DATASET_KEY])
            d = dedupe(store, "yellowstone")
            check(d["marked_duplicate"] == 1, "cross-source dedupe marks the mirrored bison")
            out = tmp / "export"
            r = export_park(store, "yellowstone", out)
            check(r["cells"]["features"] == 2 and r["cells"]["sightings_in_cells"] == 3 and r["species"]["species"] >= 3,
                  "cells.geojson and species.json baked")
            manifest = json.loads((out / "manifest.json").read_text())
            for name, meta in manifest["files"].items():
                digest = hashlib.sha256((out / name).read_bytes()).hexdigest()
                check(digest == meta["sha256"], f"manifest hash matches {name}")
    elapsed = time.time() - t0
    check(elapsed < 300, f"finished in {elapsed:.1f}s (< 300s)")


if __name__ == "__main__":
    main()
