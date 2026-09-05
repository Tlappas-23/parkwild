"""Photographs for the app: the evidence behind the cells.

PROBLEM: an aggregated hexagon proves nothing to a reader. iNaturalist
observations carry photographs with per-photo licences, and every record's
raw JSON is in the database, so the app can show the animal at the place.

CURRENT: two files. `photos_species.json` holds up to SPECIES_PHOTOS photos per
species (card art, hero, gallery); `photos_cells.json` holds up to CELL_PHOTOS
per H3 cell (the "seen here" strip). Only photos whose licence allows display
of a resized copy are included (DISPLAYABLE); "no derivatives" licences and
all-rights-reserved photos are left out entirely rather than shown as a
link, so nothing on the page is ever unlicensed. Every entry carries the
observer, the licence and the observation id, and the app prints the credit
beside the photo. Sensitive-species rules match the cells export: excluded
species get no cell photos, coarsened species attach to the coarse cell,
obscured coordinates attach to no cell (the species gallery is fine; it
shows no location).

Photo URLs are rebuilt by the app from an id, an extension and a host flag,
which keeps the cell file to a fraction of the size of full URLs.

CONSIDERED, NOT DONE: mirroring the images. Hotlinking from iNaturalist's
CDN is what its API URLs are for, and copying licensed photos into this
repository would make the repository the publisher.

UNRESOLVED: "best" photo is faves then recency; nothing here judges whether
a photo actually shows the animal well.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import h3

from .config import Suppression, canonical_species, load_suppression, load_synonyms
from .decisionlog import log_filter
from .export import H3_RES, auto_sensitive_species, suppression_for
from .storage import Store

# DISPLAYABLE — BORROWED (Creative Commons licence terms)
# Licences that permit showing a resized copy with attribution. ND ("no
# derivatives") variants are excluded because a resized copy is arguably a
# derivative; all-rights-reserved (license_code None) is excluded outright.
DISPLAYABLE = {"cc0": "CC0", "cc-by": "CC BY", "cc-by-sa": "CC BY-SA", "cc-by-nc": "CC BY-NC", "cc-by-nc-sa": "CC BY-NC-SA"}

# SPECIES_PHOTOS / CELL_PHOTOS — ARBITRARY
# Eight fills a gallery row on a phone twice over; three per cell keeps the
# cell file near a megabyte for 6,700 cells.
SPECIES_PHOTOS = 8
CELL_PHOTOS = 3

# HOSTS — MEASURED (the two CDN prefixes seen across 89,238 Yellowstone photo URLs)
HOSTS = ("https://inaturalist-open-data.s3.amazonaws.com/photos/", "https://static.inaturalist.org/photos/")
URL_RE = re.compile(r"^(https://[^/]+/photos/)(\d+)/[a-z_]+\.([A-Za-z0-9]+)$")


def parse_photo(p: dict) -> tuple[int, str, int] | None:
    """(photo_id, extension, host_index) from a raw iNaturalist photo record,
    or None if the URL is not one of the two known CDN shapes."""
    m = URL_RE.match(p.get("url") or "")
    if not m:
        return None
    host = m.group(1)
    if host not in HOSTS:
        return None
    return int(m.group(2)), m.group(3).lower(), HOSTS.index(host)


def export_photos(store: Store, park: str, out_dir: Path, *, rules: list[Suppression] | None = None, res: int = H3_RES) -> dict:
    rules = load_suppression() if rules is None else rules
    auto = auto_sensitive_species(store, park)
    synonyms = load_synonyms()
    rows = store.sql(
        """
        SELECT scientific_name, lon, lat, coordinate_status, observer, source_id, observed_on, raw_json
        FROM sightings WHERE park = ? AND source = 'inaturalist' AND duplicate_of IS NULL AND scientific_name IS NOT NULL
        """,
        [park],
    )
    n_obs = len(rows)
    n_photos = n_kept = 0
    by_species: dict[str, list[tuple]] = {}
    by_cell: dict[str, list[tuple]] = {}
    species_index: dict[str, int] = {}
    for raw_sci, lon, lat, status, observer, obs_id, on, raw in rows:
        sci = canonical_species(raw_sci, synonyms)
        o = json.loads(raw)
        photos = o.get("photos") or []
        faves = int(o.get("faves_count") or 0)
        rule = suppression_for(sci, rules, auto) or suppression_for(raw_sci, rules, auto)
        cell = None
        if status == "open" and lon is not None and not (rule is not None and rule.action == "exclude"):
            cell = h3.latlng_to_cell(lat, lon, rule.res or 6 if (rule is not None and rule.action == "coarsen") else res)
        first_kept = None
        for p in photos:
            n_photos += 1
            lic = p.get("license_code")
            parsed = parse_photo(p)
            if lic not in DISPLAYABLE or parsed is None:
                continue
            n_kept += 1
            pid, ext, host = parsed
            entry = (faves, str(on or ""), pid, ext, host, observer or "", DISPLAYABLE[lic], int(obs_id), cell)
            if first_kept is None:
                first_kept = entry    # one photo per observation in galleries and cells
        if first_kept is None:
            continue
        idx = species_index.setdefault(sci, len(species_index))
        by_species.setdefault(sci, []).append(first_kept)
        if cell is not None:
            by_cell.setdefault(cell, []).append((idx,) + first_kept)

    def best(entries: list[tuple], n: int, key_faves: int = 0) -> list[tuple]:
        """Most-faved first, then most recent. `key_faves` is the index of the
        faves field (cell entries carry a species index in front)."""
        def date_num(d: str) -> int:
            return int((d or "").replace("-", "")[:8] or 0)
        return sorted(entries, key=lambda e: (-e[key_faves], -date_num(e[key_faves + 1])))[:n]

    species_out = {
        sci: [{"i": pid, "e": ext, "h": host, "o": obs, "l": lic, "obs": oid, "d": on or None, "c": cell}
              for (faves, on, pid, ext, host, obs, lic, oid, cell) in best(entries, SPECIES_PHOTOS)]
        for sci, entries in by_species.items()
    }
    # A cell's strip is its best few photographs overall plus the best one of
    # every species photographed there, so filtering the map to elk and tapping
    # a cell shows an elk from that cell rather than three bison (E-024). The
    # first version kept the top CELL_PHOTOS only; it is kept below for the
    # comparison test.
    def cell_pick(entries: list[tuple]) -> list[tuple]:
        top = cell_pick_v1(entries)
        seen = {e[0] for e in top}
        for e in best(entries, len(entries), key_faves=1):
            if e[0] not in seen:
                top.append(e)
                seen.add(e[0])
        return top

    def cell_pick_v1(entries: list[tuple]) -> list[tuple]:
        return best(entries, CELL_PHOTOS, key_faves=1)

    cells_out = {
        cell: [[idx, pid, ext, host, obs, lic, oid, on or None]
               for (idx, faves, on, pid, ext, host, obs, lic, oid, _c) in cell_pick(entries)]
        for cell, entries in by_cell.items()
    }
    index = [sci for sci, _ in sorted(species_index.items(), key=lambda kv: kv[1])]
    common = {"park": park, "photo_hosts": list(HOSTS), "sizes": ["square", "small", "medium", "large"],
              "licence_rule": "displayed only under " + ", ".join(sorted(DISPLAYABLE.values())) + "; ND and all-rights-reserved photos are not shown"}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "photos_species.json").write_text(json.dumps({**common, "species": species_out}, separators=(",", ":")))
    entry_fields = ["species_index", "photo_id", "ext", "host", "observer", "license", "observation_id", "date"]
    (out_dir / "photos_cells.json").write_text(json.dumps({**common, "species_index": index, "entry": entry_fields, "cells": cells_out},
                                                          separators=(",", ":")))
    log_filter("export.photos", "iNaturalist photos with a displayable CC licence (no ND, no all-rights-reserved); one per observation",
               n_photos, n_kept, park=park, observations=n_obs, species_with_photos=len(species_out), cells_with_photos=len(cells_out))
    return {"observations": n_obs, "photos": n_photos, "displayable": n_kept, "species": len(species_out), "cells": len(cells_out),
            "bytes_species": (out_dir / "photos_species.json").stat().st_size, "bytes_cells": (out_dir / "photos_cells.json").stat().st_size}
