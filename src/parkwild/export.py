"""Bake the static artifacts the app consumes (BUILD_SPEC.md Phase 4).

PROBLEM: the app has no server and no database. Everything it shows must be
a file, small enough to fetch on a phone, aggregated enough to make no false
claim of precision, and verifiable so a swapped file is refused.

CURRENT:
  cells.geojson     H3 cells, one feature per (cell, species), counts, date
                    range, month histogram, source mix. Resolution 9 by default,
                    coarser for species on the suppression list; excluded
                    species never appear.
  species.json      per-species metadata and seasonality, including the
                    obscured share and the suppression treatment.
  sightings.parquet full canonical records with attribution, minus raw JSON.
  manifest.json     SHA-256 per file plus the git commit; the app compiles a
                    copy in and refuses data that does not match.

Only rows with coordinate_status='open' enter cells. Obscured and private
rows still count in species.json, flagged, because "it is here, we do not
know where" is real information.

FIRST ATTEMPT that failed: `COPY ... TO ?` with a bound parameter. DuckDB
takes a literal path there; the park key is validated and interpolated.

UNRESOLVED: one feature per (cell, species) repeats each hexagon's geometry
once per species in it. Fine at Yellowstone scale; a vector-tile build would
be the fix if a park ever has hundreds of species per cell.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import h3

from .config import ROOT, Suppression, load_suppression
from .decisionlog import log_filter
from .storage import Store

# H3_RES — BORROWED (build spec, Phase 4: "H3 resolution 9 (~170 m edge),
# comparable to the error magnitude"). Coarsened species use the resolution
# in config/suppression.toml.
H3_RES = 9


def suppression_for(name: str | None, rules: list[Suppression], auto_sensitive: set[str]) -> Suppression | None:
    """First matching rule by scientific-name prefix. Species iNaturalist obscures
    by taxon get an automatic coarsen-to-r6 unless a rule says otherwise."""
    if not name:
        return None
    for r in rules:
        if name == r.name or name.startswith(r.name + " "):
            return r
    if name in auto_sensitive:
        return Suppression(name, "", "coarsen", 6, "iNaturalist obscures this taxon by default (taxon_geoprivacy)")
    return None


def auto_sensitive_species(store: Store, park: str) -> set[str]:
    """Species with any iNaturalist observation carrying taxon_geoprivacy."""
    rows = store.sql(
        """
        SELECT DISTINCT scientific_name FROM sightings
        WHERE park = ? AND source = 'inaturalist' AND scientific_name IS NOT NULL
          AND json_extract_string(raw_json, '$.taxon_geoprivacy') IN ('obscured', 'private')
        """,
        [park],
    )
    return {r[0] for r in rows}

SIGHTING_EXPORT_COLUMNS = [
    "sighting_id", "source", "dataset", "park", "confidence_basis", "taxon_id", "scientific_name",
    "common_name", "taxon_rank", "taxon_class", "observed_at", "observed_on", "lon", "lat",
    "positional_accuracy_m", "coordinate_status", "observer", "license", "url", "attribution",
]


def _canonical_where(park_param: str = "?") -> str:
    return f"park = {park_param} AND duplicate_of IS NULL"


def cells_geojson(store: Store, park: str, out_path: Path, *, res: int = H3_RES, rules: list[Suppression] | None = None) -> dict:
    rules = load_suppression() if rules is None else rules
    auto = auto_sensitive_species(store, park)
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
    excluded: dict[str, int] = {}
    coarsened: dict[str, int] = {}
    for lon, lat, sci, common, cls, basis, on in rows:
        rule = suppression_for(sci, rules, auto)
        cell_res = res
        if rule is not None and rule.action == "exclude":
            excluded[sci] = excluded.get(sci, 0) + 1
            continue
        if rule is not None and rule.action == "coarsen":
            cell_res = rule.res or 6
            coarsened[sci] = coarsened.get(sci, 0) + 1
        cell = h3.latlng_to_cell(lat, lon, cell_res)
        key = (cell, sci)
        a = agg.setdefault(key, {
            "cell": cell, "species": sci, "common_name": common, "class": cls, "res": cell_res,
            "coarsened": cell_res != res,
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
    n_excluded = sum(excluded.values())
    log_filter("export.cells.suppression", "species suppression list + iNaturalist taxon_geoprivacy (config/suppression.toml)",
               len(rows), len(rows) - n_excluded, park=park, excluded=excluded, coarsened=coarsened)
    fc = {"type": "FeatureCollection", "features": features, "park": park, "h3_res": res,
          "suppressed": {"excluded": excluded, "coarsened": coarsened}}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fc, separators=(",", ":")))
    return {"features": len(features), "sightings_in_cells": len(rows) - n_excluded, "cells": len({k[0] for k in agg}),
            "excluded": n_excluded, "coarsened": sum(coarsened.values())}


def species_json(store: Store, park: str, out_path: Path, *, rules: list[Suppression] | None = None) -> dict:
    rules = load_suppression() if rules is None else rules
    auto = auto_sensitive_species(store, park)
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
        rule = suppression_for(sci, rules, auto)
        species.append({
            "scientific_name": sci, "common_name": common, "class": cls, "taxon_id": tid,
            "suppression": None if rule is None else {"action": rule.action, "res": rule.res, "why": rule.why},
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


# PARK_KEY — DERIVED (the TOML table-key alphabet used in config/parks.toml)
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
    files = [out_dir / "cells.geojson", out_dir / "species.json", out_dir / "sightings.parquet"]
    if (out_dir / "bias.json").exists():   # written by `track_a.py bias --write`, optional
        files.append(out_dir / "bias.json")
    write_manifest(out_dir, files, {"park": park})
    return result
