"""Track A orchestration: ingest reference sightings and deduplicate across sources.

PROBLEM: two sources that overlap (GBIF mirrors iNaturalist) and a schema
that must never double count, while never deleting a row.

CURRENT: the iNaturalist mirror is removed at the source, by GBIF dataset
key, before dedupe runs (exact, cheap). What remains is fuzzy cross-source
dedupe: same species and date, within DEDUPE_DIST_M, and either the
observer names match after normalisation or both have times within
DEDUPE_WINDOW_S. The iNaturalist row stays canonical; the other row gets
`duplicate_of` set. Nothing is deleted; exports filter on `duplicate_of IS
NULL`. Every drop is logged to reports/decision_log.jsonl.

CONSIDERED, NOT DONE: dedupe within a source. Two iNaturalist users who
both photographed the same bison are two observations by iNaturalist's own
definition, and the app counts observations, not animals.

UNRESOLVED: observer names differ in form between sources (login vs display
name), so the observer match rarely fires and the time match does most of
the work. Measured duplicate rate on Yellowstone goes in RESULTS.md.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime

from . import gbif, inaturalist
from .contracts import check_lon_lat
from .decisionlog import log_filter
from .geo import BBox, haversine_m
from .storage import Store

log = logging.getLogger(__name__)

# SOURCE_PRIORITY — ASSUMED
# Which row stays canonical when two match: the source with the richer record
# and the stable URL. iNaturalist first, then GBIF, then our own detections.
SOURCE_PRIORITY = {"inaturalist": 0, "gbif": 1, "mapillary_cv": 2}

# DEDUPE_DIST_M — ASSUMED
# Two reports of one event should land within phone-GPS error of each other.
# 200 m is generous for GPS and tight against a herd spread along a road.
# REVISIT IF: the marked-duplicate rate looks implausibly high or low.
DEDUPE_DIST_M = 200.0

# DEDUPE_WINDOW_S — ASSUMED
# One hour: a pull-out where several people photograph the same animals.
DEDUPE_WINDOW_S = 3600.0


def ingest_inaturalist(store: Store, park: str, *, place_id: int | None, bbox: BBox | None, max_records: int | None = None, batch: int = 500) -> dict:
    """Pull research-grade Mammalia + Aves observations and upsert them."""
    rows: list[dict] = []
    n_raw = n_written = 0
    status_counts: dict[str, int] = {}
    for obs in inaturalist.iter_observations(place_id=place_id, bbox=bbox, max_records=max_records):
        n_raw += 1
        row = inaturalist.normalize(obs, park)
        status_counts[row["coordinate_status"]] = status_counts.get(row["coordinate_status"], 0) + 1
        rows.append(row)
        if len(rows) >= batch:
            check_lon_lat(rows)
            n_written += store.upsert_sightings(rows)
            rows = []
    if rows:
        check_lon_lat(rows)
        n_written += store.upsert_sightings(rows)
    log_filter("track_a.inaturalist", "all research-grade Mammalia+Aves stored; obscured/private flagged, not dropped",
               n_raw, n_written, park=park, place_id=place_id, coordinate_status=status_counts)
    return {"fetched": n_raw, "written": n_written, "coordinate_status": status_counts}


def ingest_gbif(store: Store, park: str, bbox: BBox, *, classes: Iterable[str] = ("Mammalia", "Aves"),
                max_records: int | None = None, skip_datasets: tuple[str, ...] = (gbif.INAT_DATASET_KEY,), batch: int = 500) -> dict:
    """Pull GBIF occurrences for each class inside the park bbox, skipping the
    iNaturalist mirror dataset (already ingested directly)."""
    summary: dict = {}
    for cls in classes:
        class_key = gbif.CLASS_KEYS[cls]
        rows: list[dict] = []
        n_raw = n_skipped = n_written = 0
        status_counts: dict[str, int] = {}
        skipped_by: dict[str, int] = {}
        for occ in gbif.iter_occurrences(bbox, class_key, max_records=max_records):
            n_raw += 1
            ds = occ.get("datasetKey")
            if ds in skip_datasets:
                n_skipped += 1
                skipped_by[ds] = skipped_by.get(ds, 0) + 1
                continue
            row = gbif.normalize(occ, park)
            status_counts[row["coordinate_status"]] = status_counts.get(row["coordinate_status"], 0) + 1
            rows.append(row)
            if len(rows) >= batch:
                check_lon_lat(rows)
                n_written += store.upsert_sightings(rows)
                rows = []
        if rows:
            check_lon_lat(rows)
            n_written += store.upsert_sightings(rows)
        log_filter("track_a.gbif", f"{cls}: skip datasets already ingested directly ({', '.join(skip_datasets)})",
                   n_raw, n_raw - n_skipped, park=park, taxon_class=cls, skipped_by_dataset=skipped_by, coordinate_status=status_counts)
        summary[cls] = {"fetched": n_raw, "skipped_mirror": n_skipped, "written": n_written, "coordinate_status": status_counts}
    return summary


def _norm_observer(name: str | None) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def dedupe(store: Store, park: str, *, dist_m: float = DEDUPE_DIST_M, time_window_s: float = DEDUPE_WINDOW_S) -> dict:
    """Mark cross-source duplicates. Two sightings are the same event when they
    share species and date, sit within `dist_m`, and either have observers that
    match after normalisation or both have times within `time_window_s`. The
    higher-priority source (iNaturalist first) stays canonical; the other row
    gets duplicate_of set. Nothing is deleted."""
    store.clear_duplicates(park)
    rows = store.sql(
        """
        SELECT sighting_id, source, scientific_name, observed_on, observed_at, lon, lat, observer
        FROM sightings WHERE park = ? AND lon IS NOT NULL AND observed_on IS NOT NULL
        ORDER BY scientific_name, observed_on
        """,
        [park],
    )
    groups: dict[tuple, list[tuple]] = {}
    for r in rows:
        groups.setdefault((r[2], r[3]), []).append(r)
    pairs: list[tuple[str, str]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda r: (SOURCE_PRIORITY.get(r[1], 9), r[0]))
        canonical: list[tuple] = []
        for r in members:
            match = None
            for c in canonical:
                if haversine_m(r[5], r[6], c[5], c[6]) > dist_m:
                    continue
                obs_match = _norm_observer(r[7]) and _norm_observer(r[7]) == _norm_observer(c[7])
                time_match = r[4] is not None and c[4] is not None and abs((r[4] - c[4]).total_seconds()) <= time_window_s
                if obs_match or time_match:
                    match = c
                    break
            if match is not None and match[1] != r[1]:   # only cross-source; same-source dups are the source's business
                pairs.append((r[0], match[0]))
            else:
                canonical.append(r)
    n_marked = store.mark_duplicates(pairs)
    n_total = store.one("SELECT count(*) FROM sightings WHERE park = ?", [park])
    log_filter("track_a.dedupe", f"cross-source: same species+date, <= {dist_m:.0f} m, observer match or times within {time_window_s:.0f} s",
               n_total, n_total - n_marked, park=park, marked_duplicate=n_marked)
    return {"total": n_total, "marked_duplicate": n_marked}


def park_summary(store: Store, park: str) -> dict:
    return {
        "total": store.one("SELECT count(*) FROM sightings WHERE park = ?", [park]),
        "canonical": store.one("SELECT count(*) FROM sightings WHERE park = ? AND duplicate_of IS NULL", [park]),
        "by_source": store.sql("SELECT source, count(*) FROM sightings WHERE park = ? GROUP BY 1 ORDER BY 1", [park]),
        "by_class": store.sql("SELECT taxon_class, count(*) FROM sightings WHERE park = ? GROUP BY 1 ORDER BY 2 DESC", [park]),
        "by_status": store.sql("SELECT coordinate_status, count(*) FROM sightings WHERE park = ? GROUP BY 1 ORDER BY 2 DESC", [park]),
        "species": store.one("SELECT count(DISTINCT scientific_name) FROM sightings WHERE park = ? AND taxon_rank IN ('species','subspecies')", [park]),
        "date_range": store.sql("SELECT min(observed_on), max(observed_on) FROM sightings WHERE park = ?", [park])[0],
        "generated": datetime.now().isoformat(timespec="seconds"),
    }
