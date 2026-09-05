"""
Bake the static artifacts the app consumes (BUILD_SPEC.md, Phase 4):

  cells.geojson     H3 resolution-9 cells, one feature per (cell, species),
                    with counts, date range, month histogram and source mix
  species.json      per-species metadata and seasonality
  sightings.parquet full canonical records with attribution, minus raw JSON
  manifest.json     sha256 per file + build info, so the app can refuse
                    tampered data (SECURITY.md)

Only rows with coordinate_status='open' go into cells. Obscured and private
rows still count in species.json totals, flagged as such, because "we know it
is here, we do not know where" is real information.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import h3

from .config import ROOT
from .decisionlog import log_filter
from .storage import Store

H3_RES = 9   # ~174 m edge; comparable to the positional error we expect

SIGHTING_EXPORT_COLUMNS = [
    "sighting_id", "source", "dataset", "park", "confidence_basis", "taxon_id", "scientific_name",
    "common_name", "taxon_rank", "taxon_class", "observed_at", "observed_on", "lon", "lat",
    "positional_accuracy_m", "coordinate_status", "observer", "license", "url", "attribution",
]


def _canonical_where(park_param: str = "?") -> str:
    return f"park = {park_param} AND duplicate_of IS NULL"


def cells_geojson(store: Store, park: str, out_path: Path, *, res: int = H3_RES) -> dict:
    rows = store.sql(
        f"""
        SELECT lon, lat, scientific_name, common_name, taxon_class, confidence_basis, observed_on
        FROM sightings
        WHERE {_canonical_where()} AND coordinate_status = 'open' AND lon IS NOT NULL AND scientific_name IS NOT NULL
        """,
        [park],
    )
    n_canonical = store.one(f"SELECT count(*) FROM sightings WHERE {_canonical_where()}", [park])
    log_filter("export.cells", "canonical rows with open coordinates and a taxon name", n_canonical, len(rows), park=park, h3_res=res)

    agg: dict[tuple[str, str], dict] = {}
    for lon, lat, sci, common, cls, basis, on in rows:
        cell = h3.latlng_to_cell(lat, lon, res)
        key = (cell, sci)
        a = agg.setdefault(key, {
            "cell": cell, "species": sci, "common_name": common, "class": cls,
            "count": 0, "human_verified": 0, "model_predicted": 0,
            "first": None, "last": None, "months": [0] * 12,
        })
        a["count"] += 1
        a[basis] = a.get(basis, 0) + 1
        if on:
            d = str(on)
            a["first"] = d if a["first"] is None or d < a["first"] else a["first"]
            a["last"] = d if a["last"] is None or d > a["last"] else a["last"]
            a["months"][int(d[5:7]) - 1] += 1
        if common and not a["common_name"]:
            a["common_name"] = common

    features = []
    for a in agg.values():
        boundary = h3.cell_to_boundary(a["cell"])           # [(lat, lng), ...]
        ring = [[lng, lat] for lat, lng in boundary] + [[boundary[0][1], boundary[0][0]]]
        features.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": a})
    fc = {"type": "FeatureCollection", "features": features, "park": park, "h3_res": res}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fc, separators=(",", ":")))
    return {"features": len(features), "sightings_in_cells": len(rows), "cells": len({k[0] for k in agg})}


def species_json(store: Store, park: str, out_path: Path) -> dict:
    rows = store.sql(
        f"""
        SELECT scientific_name, any_value(common_name), any_value(taxon_class), any_value(taxon_id),
               count(*) AS n,
               sum(CASE WHEN coordinate_status = 'open' THEN 1 ELSE 0 END),
               sum(CASE WHEN coordinate_status = 'obscured' THEN 1 ELSE 0 END),
               sum(CASE WHEN source = 'inaturalist' THEN 1 ELSE 0 END),
               sum(CASE WHEN source = 'gbif' THEN 1 ELSE 0 END),
               sum(CASE WHEN source = 'mapillary_cv' THEN 1 ELSE 0 END),
               sum(CASE WHEN confidence_basis = 'human_verified' THEN 1 ELSE 0 END),
               sum(CASE WHEN confidence_basis = 'model_predicted' THEN 1 ELSE 0 END),
               min(observed_on), max(observed_on),
               list(month(observed_on))
        FROM sightings
        WHERE {_canonical_where()} AND scientific_name IS NOT NULL AND taxon_rank IN ('species', 'subspecies')
        GROUP BY scientific_name ORDER BY n DESC
        """,
        [park],
    )
    species = []
    for sci, common, cls, tid, n, n_open, n_obs, n_inat, n_gbif, n_cv, n_hv, n_mp, first, last, months in rows:
        hist = [0] * 12
        for m in months or []:
            if m:
                hist[int(m) - 1] += 1
        species.append({
            "scientific_name": sci, "common_name": common, "class": cls, "taxon_id": tid,
            "sightings": n, "open_coordinates": n_open, "obscured_coordinates": n_obs,
            "sources": {"inaturalist": n_inat, "gbif": n_gbif, "mapillary_cv": n_cv},
            "confidence_basis": {"human_verified": n_hv, "model_predicted": n_mp},
            "first": str(first) if first else None, "last": str(last) if last else None,
            "months": hist,
            "model": None,   # 3D asset reference, Phase 6
        })
    payload = {"park": park, "generated": datetime.now(UTC).isoformat(timespec="seconds"), "species": species,
               "notes": {"recall": "unmeasured", "obscured": "coordinates fuzzed by the source for sensitive taxa; counted, never mapped"}}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, separators=(",", ":")))
    return {"species": len(species)}


PARK_KEY = re.compile(r"^[a-z0-9_]+$")


def sightings_parquet(store: Store, park: str, out_path: Path) -> dict:
    """DuckDB's COPY takes literal paths, not bound parameters, so the park key
    and path are interpolated. The key is validated against the TOML-key
    alphabet first; the path is single-quote escaped."""
    if not PARK_KEY.match(park):
        raise ValueError(f"park key {park!r} is not a plain identifier")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ", ".join(SIGHTING_EXPORT_COLUMNS)
    path_sql = str(out_path).replace("'", "''")
    store.con.execute(
        f"COPY (SELECT {cols} FROM sightings WHERE park = '{park}' AND duplicate_of IS NULL "
        f"ORDER BY observed_on, sighting_id) TO '{path_sql}' (FORMAT PARQUET)"
    )
    n = store.one(f"SELECT count(*) FROM read_parquet('{path_sql}')")
    return {"rows": n}


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=True).stdout.strip()
    except Exception:
        return None


def write_manifest(out_dir: Path, files: list[Path], extra: dict | None = None) -> Path:
    entries = {}
    for f in files:
        data = f.read_bytes()
        entries[f.name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    manifest = {"built": datetime.now(UTC).isoformat(timespec="seconds"), "git_commit": _git_commit(), "files": entries, **(extra or {})}
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    return path


def export_park(store: Store, park: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "cells": cells_geojson(store, park, out_dir / "cells.geojson"),
        "species": species_json(store, park, out_dir / "species.json"),
        "sightings": sightings_parquet(store, park, out_dir / "sightings.parquet"),
    }
    write_manifest(out_dir, [out_dir / "cells.geojson", out_dir / "species.json", out_dir / "sightings.parquet"], {"park": park})
    return result
