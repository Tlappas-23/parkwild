"""Where each animal has been seen, park by park: species_index.json.

The species page searched one park at a time, because every park's files are
separate. The owner asked to search an animal and see where in each park it
turns up most, and to jump there. Doing that at query time would mean pulling
every park's cells (a few MB each), so this module rolls the files the app
ships into one small index at publish time: for each species, the parks it
was recorded in, how many sightings there, how many cells, and the busiest
cells with their centres. The app fetches it once, on demand, and checks its
hash the way it checks every other file (the hash rides in parks.json).

Obscured coordinates stay obscured: the cells are the shipped ones, coarsened
where a species is sensitive, and a species that is not mapped at all carries
counts but no places. Nothing here is a model prediction unless the shipped
cell says so; the model-predicted count travels beside the human-verified one.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from .config import ROOT

log = logging.getLogger(__name__)

APP_DATA_DIR = ROOT / "app" / "public" / "data"      # what the app ships; the index must agree with it
INDEX_PATH = APP_DATA_DIR / "species_index.json"
# TOP_CELLS — ARBITRARY (busiest cells kept per species and park; the jump lands on the first)
TOP_CELLS = 3
# COORD_DECIMALS — ARBITRARY (four decimals is about 10 m, finer than any cell)
COORD_DECIMALS = 4


def centroid(ring: list[list[float]]) -> tuple[float, float]:
    """Mean of a ring's vertices (closing vertex dropped): good enough for a hexagon."""
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    n = max(1, len(pts))
    return sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n


def park_dirs(data_dir: Path) -> list[Path]:
    return sorted(d for d in data_dir.iterdir() if d.is_dir() and (d / "species.json").exists() and (d / "cells.geojson").exists())


def build_species_index(data_dir: Path = APP_DATA_DIR, out_path: Path = INDEX_PATH, top_cells: int = TOP_CELLS) -> dict:
    parks: dict[str, dict] = {}
    species: dict[str, dict] = {}
    non_species = 0                                   # genus- and family-level records: in the cells, not in species.json
    for d in park_dirs(data_dir):
        key = d.name
        manifest = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        parks[key] = {"name": manifest.get("name") or key, "state": manifest.get("state")}
        for s in json.loads((d / "species.json").read_text())["species"]:
            e = species.setdefault(s["scientific_name"], {"n": s["scientific_name"], "c": None, "k": s.get("class"), "names": set(), "parks": {}})
            if e["c"] is None and s.get("common_name"):
                e["c"] = s["common_name"]
            for nm in (s.get("common_name"), *s.get("aliases", []), *s.get("other_names", [])):
                if nm:
                    e["names"].add(nm)
            sup = s.get("suppression") or None
            e["parks"][key] = {"s": s["sightings"], "hv": s["confidence_basis"]["human_verified"], "mp": s["confidence_basis"]["model_predicted"],
                               "x": sup["action"] if sup else None, "cells": 0, "top": []}
        cells = json.loads((d / "cells.geojson").read_text())
        names = [x["n"] for x in cells["species_index"]]
        for f in cells["features"]:
            p = f["properties"]
            lon, lat = centroid(f["geometry"]["coordinates"][0])
            for idx, count, _hv, _mp, _y0, _y1 in p["sp"]:
                e = species.get(names[idx])
                if not e or key not in e["parks"]:
                    non_species += 1
                    continue
                pk = e["parks"][key]
                pk["cells"] += 1
                top = pk["top"]
                top.append([round(lon, COORD_DECIMALS), round(lat, COORD_DECIMALS), count, p["cell"], p["res"]])
                top.sort(key=lambda t: -t[2])
                del top[top_cells:]
    entries = []
    for e in species.values():
        total = sum(p["s"] for p in e["parks"].values())
        other = sorted(n for n in e["names"] if n != e["c"])
        entries.append({"n": e["n"], "c": e["c"], "k": e["k"], "other": other, "total": total, "parks": e["parks"]})
    entries.sort(key=lambda x: (-x["total"], x["n"]))
    payload = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "parks": parks,
        "top_cells": top_cells,
        "species": entries,
        "notes": {
            "cells": "The busiest cells are the shipped ones: coarsened where a species is sensitive; "
                     "a species that is not mapped carries counts but no places.",
            "recall": "Counts are what people recorded, not how many animals there are.",
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    if non_species:
        log.info("%d cell entries are genus- or family-level records (Laridae, Aves…) that species.json leaves out; skipped", non_species)
    return {"species": len(entries), "parks": len(parks), "bytes": out_path.stat().st_size, "non_species_cell_entries": non_species}


def species_index_stamp(path: Path = INDEX_PATH) -> dict | None:
    """The hash parks.json carries so the app can verify the index it fetches."""
    if not path.exists():
        return None
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
