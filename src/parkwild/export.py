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

RESOLVED (E-017): the first cells.geojson repeated geometry per species and
weighed 10.9 MB for Yellowstone. One feature per cell with a species index
and five-decimal coordinates is the current shape; size is in the ledger.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import h3

from .config import ROOT, Suppression, canonical_species, get_park, load_suppression, load_synonyms
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


# AUTO_SENSITIVE_SHARE — MEASURED (2026-09-05, Yellowstone iNaturalist rows)
#
# Share of a species' observations carrying taxon_geoprivacy:
#     grizzly 99%   wolf 99%   bighorn 89%   river otter 100%   great grey owl 100%
#     bison 0%      black bear 3%   coyote 2%   moose 0%   marmot 0%   starling 3%
#
# iNaturalist applies taxon geoprivacy per place, so a common species picks up
# a few flagged observations from a county where it has a status. The first
# rule ("any flagged observation") coarsened bison and starlings (E-019). A
# majority rule separates the two groups with nothing in between.
# REVISIT IF: a species lands between 20% and 80% in a new park.
AUTO_SENSITIVE_SHARE = 0.5


def auto_sensitive_species(store: Store, park: str, *, min_share: float = AUTO_SENSITIVE_SHARE) -> set[str]:
    """Species whose iNaturalist observations are mostly taxon-obscured."""
    rows = store.sql(
        """
        SELECT scientific_name,
               avg(CASE WHEN json_extract_string(raw_json, '$.taxon_geoprivacy') IN ('obscured', 'private') THEN 1.0 ELSE 0.0 END) AS share
        FROM sightings
        WHERE park = ? AND source = 'inaturalist' AND scientific_name IS NOT NULL
        GROUP BY scientific_name HAVING share >= ?
        """,
        [park, min_share],
    )
    return {r[0] for r in rows}

SIGHTING_EXPORT_COLUMNS = [
    "sighting_id", "source", "dataset", "park", "confidence_basis", "taxon_id", "scientific_name",
    "common_name", "taxon_rank", "taxon_class", "observed_at", "observed_on", "lon", "lat",
    "positional_accuracy_m", "coordinate_status", "observer", "license", "url", "attribution",
]


def _canonical_where(park_param: str = "?") -> str:
    return f"park = {park_param} AND duplicate_of IS NULL"



# Common names. iNaturalist carries one curated name per taxon and a different
# one per subspecies, which is why "American Elk" (the nelsoni subspecies
# label) and "Wapiti" (the species) both arrive under Cervus canadensis once
# subspecies collapse. GBIF vernaculars vary by dataset and can be junk
# ("Canada Goose unknown" for the Cackling Goose). So the display name is the
# one most iNaturalist rows used, and GBIF names count only when iNaturalist
# never recorded the species. The first version took the first name seen per
# file, so the map said "American Elk" while the species list said "Wapiti"
# for the same animal, and the Yellow Warbler wore its "Mangrove Warbler"
# subspecies label (E-024).
def common_name_votes(store: Store, park: str) -> dict[str, dict[str, dict[str, int]]]:
    """One vote table for the whole park, over every canonical row, open or
    obscured, so cells.geojson and species.json cannot disagree. The first
    pass voted inside each exporter, and the cells file, which only sees open
    coordinates, named the Smokies' elk from its single open row (E-024)."""
    rows = store.sql(
        f"""
        SELECT scientific_name, common_name, source, count(*)
        FROM sightings WHERE {_canonical_where()} AND scientific_name IS NOT NULL
        GROUP BY 1, 2, 3
        """,
        [park],
    )
    synonyms = load_synonyms()
    votes: dict[str, dict[str, dict[str, int]]] = {}
    for raw_sci, common, source, n in rows:
        v = votes.setdefault(canonical_species(raw_sci, synonyms), {})
        if common:
            tier = v.setdefault("inaturalist" if source == "inaturalist" else "other", {})
            tier[common] = tier.get(common, 0) + n
    return votes


def pick_common_name(votes: dict[str, dict[str, int]]) -> str | None:
    for tier in ("inaturalist", "other"):
        if votes.get(tier):
            return max(votes[tier], key=lambda n: (votes[tier][n], n))
    return None


def other_common_names(votes: dict[str, dict[str, int]], chosen: str | None) -> list[str]:
    """Every other name the records used, so a search for "elk" finds Wapiti."""
    names = {n for tier in votes.values() for n in tier}
    names.discard(chosen)
    return sorted(names)


def cells_geojson(store: Store, park: str, out_path: Path, *, res: int = H3_RES, rules: list[Suppression] | None = None) -> dict:
    """One feature per H3 cell, with a compact per-species list inside it.

    FIRST VERSION (E-017) emitted one feature per (cell, species) and repeated
    each hexagon's geometry once per species: 10.9 MB for Yellowstone, which
    no phone loads in three seconds. Now geometry appears once per cell,
    coordinates carry five decimals (about a metre), species names live in a
    single index on the collection, and each species entry is a short array:
    [species_index, count, human_verified, model_predicted, first_year, last_year].
    """
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

    synonyms = load_synonyms()
    names = common_name_votes(store, park)
    species_index: dict[str, int] = {}
    species_class: dict[str, str | None] = {}
    cells: dict[str, dict] = {}
    excluded: dict[str, int] = {}
    coarsened: dict[str, int] = {}
    merged: dict[str, str] = {}
    for lon, lat, raw_sci, _common, cls, basis, on in rows:
        sci = canonical_species(raw_sci, synonyms)
        if sci != raw_sci:
            merged[raw_sci] = sci
        rule = suppression_for(sci, rules, auto) or suppression_for(raw_sci, rules, auto)
        cell_res = res
        if rule is not None and rule.action == "exclude":
            excluded[sci] = excluded.get(sci, 0) + 1
            continue
        if rule is not None and rule.action == "coarsen":
            cell_res = rule.res or 6
            coarsened[sci] = coarsened.get(sci, 0) + 1
        idx = species_index.setdefault(sci, len(species_index))
        species_class.setdefault(sci, cls)
        cell = h3.latlng_to_cell(lat, lon, cell_res)
        c = cells.setdefault(cell, {"res": cell_res, "count": 0, "hv": 0, "mp": 0, "y0": None, "y1": None, "sp": {}})
        e = c["sp"].setdefault(idx, [idx, 0, 0, 0, None, None])
        year = int(str(on)[:4]) if on else None
        for target in (c, e):
            if isinstance(target, dict):
                target["count"] += 1
                target["hv" if basis == "human_verified" else "mp"] += 1
                if year is not None:
                    target["y0"] = year if target["y0"] is None or year < target["y0"] else target["y0"]
                    target["y1"] = year if target["y1"] is None or year > target["y1"] else target["y1"]
            else:
                target[1] += 1
                target[2 if basis == "human_verified" else 3] += 1
                if year is not None:
                    target[4] = year if target[4] is None or year < target[4] else target[4]
                    target[5] = year if target[5] is None or year > target[5] else target[5]

    features = []
    for cell, c in cells.items():
        boundary = h3.cell_to_boundary(cell)           # [(lat, lng), ...]
        ring = [[round(lng, 5), round(lat, 5)] for lat, lng in boundary]
        ring.append(ring[0])
        sp = sorted(c["sp"].values(), key=lambda e: -e[1])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"cell": cell, "res": c["res"], "coarsened": c["res"] != res, "count": c["count"],
                           "hv": c["hv"], "mp": c["mp"], "y0": c["y0"], "y1": c["y1"], "sp": sp},
        })
    n_excluded = sum(excluded.values())
    log_filter("export.cells.suppression", "species suppression list + iNaturalist taxon_geoprivacy (config/suppression.toml)",
               len(rows), len(rows) - n_excluded, park=park, excluded=excluded, coarsened=coarsened)
    log_filter("export.cells.taxonomy", "subspecies collapsed to species; GBIF spellings mapped to iNaturalist (config/taxonomy.toml)",
               len(rows), len(rows), park=park, merged_names=merged)
    index = [{"n": sci, "c": pick_common_name(names.get(sci, {})), "k": species_class[sci]}
             for sci, _ in sorted(species_index.items(), key=lambda kv: kv[1])]
    fc = {"type": "FeatureCollection", "features": features, "park": park, "h3_res": res, "species_index": index,
          "entry": ["species_index", "count", "human_verified", "model_predicted", "first_year", "last_year"],
          "suppressed": {"excluded": excluded, "coarsened": coarsened}, "merged_names": merged}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fc, separators=(",", ":")))
    return {"features": len(features), "sightings_in_cells": len(rows) - n_excluded, "cells": len(cells),
            "species": len(index), "excluded": n_excluded, "coarsened": sum(coarsened.values()), "bytes": out_path.stat().st_size}




def species_json(store: Store, park: str, out_path: Path, *, rules: list[Suppression] | None = None) -> dict:
    """Per-species metadata after name normalisation, so 'Bos bison', 'Bos
    bison bison' and 'Bison bison' are one species with one count."""
    rules = load_suppression() if rules is None else rules
    auto = auto_sensitive_species(store, park)
    synonyms = load_synonyms()
    names = common_name_votes(store, park)
    rows = store.sql(
        f"""
        SELECT scientific_name, common_name, taxon_class, taxon_id, coordinate_status, source, confidence_basis, observed_on
        FROM sightings
        WHERE {_canonical_where()} AND scientific_name IS NOT NULL
          AND (taxon_rank IN ('species', 'subspecies') OR source = 'mapillary_cv')
        """,
        [park],
    )
    # Model-predicted rows that could not be named carry the class "Mammalia" with
    # the common name "unidentified large mammal (model)"; they are kept as their
    # own entry so the model badge counts are visible in the species list.
    agg: dict[str, dict] = {}
    for raw_sci, _common, cls, tid, status, source, basis, on in rows:
        sci = canonical_species(raw_sci, synonyms)
        a = agg.setdefault(sci, {
            "scientific_name": sci, "common_name": None, "class": cls, "taxon_id": None,
            "sightings": 0, "open_coordinates": 0, "obscured_coordinates": 0,
            "sources": {"inaturalist": 0, "gbif": 0, "mapillary_cv": 0},
            "confidence_basis": {"human_verified": 0, "model_predicted": 0},
            "first": None, "last": None, "months": [0] * 12, "aliases": set(),
        })
        a["sightings"] += 1
        if status == "open":
            a["open_coordinates"] += 1
        elif status == "obscured":
            a["obscured_coordinates"] += 1
        a["sources"][source] = a["sources"].get(source, 0) + 1
        a["confidence_basis"][basis] = a["confidence_basis"].get(basis, 0) + 1
        if tid and source == "inaturalist" and raw_sci == sci:
            a["taxon_id"] = tid
        if raw_sci != sci:
            a["aliases"].add(raw_sci)
        if on:
            d = str(on)
            a["first"] = d if a["first"] is None or d < a["first"] else a["first"]
            a["last"] = d if a["last"] is None or d > a["last"] else a["last"]
            a["months"][int(d[5:7]) - 1] += 1
    species = []
    for sci, a in sorted(agg.items(), key=lambda kv: -kv[1]["sightings"]):
        rule = suppression_for(sci, rules, auto)
        common = pick_common_name(names.get(sci, {}))   # iNaturalist majority; GBIF only as a fallback
        species.append({
            "scientific_name": sci, "common_name": common, "class": a["class"], "taxon_id": a["taxon_id"],
            "aliases": sorted(a["aliases"]),
            "other_names": other_common_names(names.get(sci, {}), common),
            "suppression": None if rule is None else {"action": rule.action, "res": rule.res, "why": rule.why},
            "sightings": a["sightings"], "open_coordinates": a["open_coordinates"], "obscured_coordinates": a["obscured_coordinates"],
            "sources": a["sources"], "confidence_basis": a["confidence_basis"],
            "first": a["first"], "last": a["last"], "months": a["months"],
        })
    payload = {"park": park, "generated": datetime.now(UTC).isoformat(timespec="seconds"), "species": species,
               "notes": {"recall": "unmeasured",
                         "obscured": "coordinates fuzzed by the source for sensitive taxa; counted, never mapped",
                         "names": "subspecies collapsed to species; GBIF backbone spellings mapped to iNaturalist's (config/taxonomy.toml)"}}
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


# PARK_FILES — DERIVED (every file the exporters and the landmarks command write)
# Presence decides what the manifest covers: bias.json exists only after the
# imagery track ran, landmarks.json and boundary.geojson only after
# `track_a.py landmarks`, roads.json only after `track_a.py roads`.
PARK_FILES = ("cells.geojson", "species.json", "sightings.parquet", "photos_species.json", "photos_cells.json", "places.json", "climate.json",
              "bias.json", "landmarks.json", "boundary.geojson", "roads.json", "camera_pass.json", "amenities.json")


def write_park_manifest(out_dir: Path, park: str) -> Path:
    """Hash every data file present so the app can refuse a swapped one. The
    park's display name rides along so the app can list parks from the
    manifests baked into it, without a second config file."""
    p = get_park(park)
    files = [out_dir / name for name in PARK_FILES if (out_dir / name).exists()]
    return write_manifest(out_dir, files, {"park": park, "name": p.name, "state": p.state})


def export_park(store: Store, park: str, out_dir: Path) -> dict:
    from .photos import export_photos  # local import: photos depends on this module's helpers
    from .trackb_export import camera_pass_json

    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "cells": cells_geojson(store, park, out_dir / "cells.geojson"),
        "species": species_json(store, park, out_dir / "species.json"),
        "sightings": sightings_parquet(store, park, out_dir / "sightings.parquet"),
        "photos": export_photos(store, park, out_dir),
        "camera_pass": camera_pass_json(store, park, out_dir / "camera_pass.json"),
    }
    write_park_manifest(out_dir, park)
    return result
