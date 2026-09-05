"""DuckDB persistence. One file, a handful of tables, no ORM.

PROBLEM: one place for the crawl index, the pixels fetched, the model output,
the human verdicts and the reference sightings, such that a rerun never
destroys evidence and every published number can be traced back to rows.

FIRST ATTEMPTS, both replaced:
- `INSERT OR REPLACE` on the raw prediction tables. A rerun with different
  thresholds would have rewritten history. Now `INSERT OR IGNORE` on
  `predictions_raw` / `detections_raw` (ADR-0007); a new model version is a
  new row; corrections go to `manual_review`.
- `setseed()` + `random()` for a reproducible download sample. Two
  consecutive calls returned different orders (E-003). Kept below as
  `images_pending_download_v1`; the current version orders on
  `hash(image_id || seed)`, which is stable across runs and machines.

ALSO LEARNED: a positional `INSERT ... VALUES` once swapped lat and lon in an
early scaffold. Every insert here names its columns.

CURRENT: tables in the SCHEMA string; `variant` distinguishes a whole frame
('full') from a panorama slice ('yaw090'); the `sightings` table is the one
shape both tracks write (ADR-0002); `_migrate` recreates only *empty*
pre-variant tables and refuses to touch populated ones.

UNRESOLVED: DuckDB allows one writer process per file. A long ingest blocks
every other script for its duration; the Track A ingest and Track B download
cannot run at the same time. Acceptable for one machine; a queue would be
needed for more.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from .config import DB_PATH
from .geo import BBox

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    image_id               VARCHAR PRIMARY KEY,
    corridor               VARCHAR,
    lon                    DOUBLE,
    lat                    DOUBLE,
    lon_raw                DOUBLE,
    lat_raw                DOUBLE,
    position_source        VARCHAR,          -- 'computed' (SfM) or 'gps'
    captured_at_ms         BIGINT,
    captured_at            TIMESTAMP,        -- UTC
    compass_angle          DOUBLE,
    computed_compass_angle DOUBLE,
    camera_type            VARCHAR,          -- perspective | fisheye | equirectangular/spherical
    is_pano                BOOLEAN,
    make                   VARCHAR,
    model                  VARCHAR,
    width                  INTEGER,
    height                 INTEGER,
    quality_score          DOUBLE,
    sequence_id            VARCHAR,
    creator_id             VARCHAR,
    creator_username       VARCHAR,
    license                VARCHAR NOT NULL, -- 'CC BY-SA 4.0'
    source_url             VARCHAR NOT NULL, -- Mapillary image page, for attribution links
    thumb_1024_url         VARCHAR,
    thumb_2048_url         VARCHAR,
    thumb_original_url     VARCHAR,
    mapillary_detections   VARCHAR,          -- JSON list of Mapillary's own segmentation labels, if requested
    fetched_at             TIMESTAMP,
    raw_json               VARCHAR           -- the full API record, as returned
);

CREATE TABLE IF NOT EXISTS tiles (
    tile_id    VARCHAR PRIMARY KEY,
    corridor   VARCHAR,
    min_lon    DOUBLE,
    min_lat    DOUBLE,
    max_lon    DOUBLE,
    max_lat    DOUBLE,
    status     VARCHAR,     -- done | split | capped | error
    n_images   INTEGER,
    fetched_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS downloads (
    image_id      VARCHAR PRIMARY KEY,
    local_path    VARCHAR,
    size_kind     VARCHAR,   -- original | 2048 | 1024 | cached
    width         INTEGER,
    height        INTEGER,
    bytes         BIGINT,
    sha256        VARCHAR,
    error         VARCHAR,   -- NULL on success
    downloaded_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    run_id           VARCHAR PRIMARY KEY,
    corridor         VARCHAR,
    population       VARCHAR,   -- perspective | pano
    model_version    VARCHAR,
    speciesnet_version VARCHAR,
    backend          VARCHAR,   -- cuda | mps | cpu | kaggle | unknown
    image_dir        VARCHAR,
    predictions_json VARCHAR,
    n_files          INTEGER,
    country          VARCHAR,
    admin1_region    VARCHAR,
    batch_size       INTEGER,
    exit_code        INTEGER,
    started_at       TIMESTAMP,
    finished_at      TIMESTAMP,
    notes            VARCHAR
);

CREATE TABLE IF NOT EXISTS predictions_raw (
    image_id          VARCHAR,
    model_version     VARCHAR,
    variant           VARCHAR NOT NULL DEFAULT 'full',   -- full | yaw000 | yaw090 | yaw180 | yaw270
    run_id            VARCHAR,
    prediction        VARCHAR,   -- SpeciesNet's final ensemble label (full 7-part string)
    prediction_score  DOUBLE,
    prediction_source VARCHAR,   -- 'classifier' | 'detector' | ... as emitted
    top5_classes      VARCHAR,   -- JSON array of label strings
    top5_scores       VARCHAR,   -- JSON array of floats
    n_detections      INTEGER,
    max_animal_conf   DOUBLE,    -- highest 'animal' detection confidence, NULL if none
    failures          VARCHAR,   -- JSON, non-NULL if SpeciesNet reported a failure
    raw_json          VARCHAR,
    predicted_at      TIMESTAMP,
    PRIMARY KEY (image_id, model_version, variant)
);

CREATE TABLE IF NOT EXISTS detections_raw (
    image_id      VARCHAR,
    model_version VARCHAR,
    variant       VARCHAR NOT NULL DEFAULT 'full',
    det_idx       INTEGER,
    category      VARCHAR,   -- '1' animal, '2' human, '3' vehicle
    label         VARCHAR,
    conf          DOUBLE,
    bbox_x        DOUBLE,    -- normalised [0,1]: x_min, y_min, width, height
    bbox_y        DOUBLE,
    bbox_w        DOUBLE,
    bbox_h        DOUBLE,
    PRIMARY KEY (image_id, model_version, variant, det_idx)
);

CREATE TABLE IF NOT EXISTS manual_review (
    image_id       VARCHAR,
    variant        VARCHAR NOT NULL DEFAULT 'full',
    det_idx        INTEGER,
    reviewer       VARCHAR,
    verdict        VARCHAR,   -- tp | fp | unsure
    true_species   VARCHAR,   -- what I think it is, free text
    species_agree  VARCHAR,   -- yes | rollup | no | na
    est_distance_m DOUBLE,
    notes          VARCHAR,
    reviewed_at    TIMESTAMP,
    PRIMARY KEY (image_id, variant, det_idx, reviewer)
);

CREATE TABLE IF NOT EXISTS sightings (
    sighting_id           VARCHAR PRIMARY KEY,   -- '<source>:<source_id>'
    source                VARCHAR NOT NULL,      -- inaturalist | gbif | mapillary_cv
    source_id             VARCHAR NOT NULL,
    dataset               VARCHAR,               -- GBIF datasetKey, 'inaturalist', or a run_id
    park                  VARCHAR,
    confidence_basis      VARCHAR NOT NULL,      -- human_verified | model_predicted
    taxon_id              VARCHAR,
    scientific_name       VARCHAR,
    common_name           VARCHAR,
    taxon_rank            VARCHAR,
    taxon_class           VARCHAR,               -- Mammalia | Aves
    observed_at           TIMESTAMP,             -- UTC, NULL if only a date is known
    observed_on           DATE,
    lon                   DOUBLE,
    lat                   DOUBLE,
    positional_accuracy_m DOUBLE,
    coordinate_status     VARCHAR NOT NULL,      -- open | obscured | private | missing
    observer              VARCHAR,
    license               VARCHAR,
    url                   VARCHAR,
    attribution           VARCHAR,               -- display-ready credit line
    duplicate_of          VARCHAR,               -- canonical sighting_id, NULL if this row is canonical
    fetched_at            TIMESTAMP,
    raw_json              VARCHAR
);
"""

IMAGE_COLUMNS = [
    "image_id", "corridor", "lon", "lat", "lon_raw", "lat_raw", "position_source",
    "captured_at_ms", "captured_at", "compass_angle", "computed_compass_angle",
    "camera_type", "is_pano", "make", "model", "width", "height", "quality_score",
    "sequence_id", "creator_id", "creator_username", "license", "source_url",
    "thumb_1024_url", "thumb_2048_url", "thumb_original_url", "mapillary_detections",
    "fetched_at", "raw_json",
]
TILE_COLUMNS = ["tile_id", "corridor", "min_lon", "min_lat", "max_lon", "max_lat", "status", "n_images", "fetched_at"]
DOWNLOAD_COLUMNS = ["image_id", "local_path", "size_kind", "width", "height", "bytes", "sha256", "error", "downloaded_at"]
RUN_COLUMNS = [
    "run_id", "corridor", "population", "model_version", "speciesnet_version", "backend", "image_dir",
    "predictions_json", "n_files", "country", "admin1_region", "batch_size", "exit_code",
    "started_at", "finished_at", "notes",
]
PREDICTION_COLUMNS = [
    "image_id", "model_version", "variant", "run_id", "prediction", "prediction_score",
    "prediction_source", "top5_classes", "top5_scores", "n_detections",
    "max_animal_conf", "failures", "raw_json", "predicted_at",
]
DETECTION_COLUMNS = [
    "image_id", "model_version", "variant", "det_idx", "category", "label", "conf",
    "bbox_x", "bbox_y", "bbox_w", "bbox_h",
]
REVIEW_COLUMNS = [
    "image_id", "variant", "det_idx", "reviewer", "verdict", "true_species", "species_agree",
    "est_distance_m", "notes", "reviewed_at",
]
SIGHTING_COLUMNS = [
    "sighting_id", "source", "source_id", "dataset", "park", "confidence_basis",
    "taxon_id", "scientific_name", "common_name", "taxon_rank", "taxon_class",
    "observed_at", "observed_on", "lon", "lat", "positional_accuracy_m", "coordinate_status",
    "observer", "license", "url", "attribution", "duplicate_of", "fetched_at", "raw_json",
]

# Tables whose rows must never change once written (ADR-0007).
APPEND_ONLY_TABLES = ("predictions_raw", "detections_raw")

POPULATION_FILTER = {
    "perspective": "NOT coalesce(is_pano, false)",
    "pano": "coalesce(is_pano, false)",
}
VARIANT_FILTER = {
    "perspective": "variant = 'full'",
    "pano": "variant LIKE 'yaw%'",
}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Store:
    def __init__(self, path: Path | str = DB_PATH, *, read_only: bool = False) -> None:
        path = str(path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(path, read_only=read_only)
        if not read_only:
            self._migrate()
            self.con.execute(SCHEMA)

    def _migrate(self) -> None:
        """The scaffold's first schema had no `variant` column. Those tables are
        recreated only if they are empty; a populated old-schema table is a
        stop-and-ask, never a silent drop."""
        existing = {r[0] for r in self.con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        for table in ("predictions_raw", "detections_raw", "manual_review"):
            if table not in existing:
                continue
            cols = {r[0] for r in self.con.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'").fetchall()}
            if "variant" in cols:
                continue
            n = self.con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            if n:
                raise RuntimeError(f"{table} has {n} rows in the pre-variant schema; migrate by hand, not by dropping")
            self.con.execute(f"DROP TABLE {table}")

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---- generic helpers -----------------------------------------------------

    def sql(self, query: str, params: Iterable[Any] | None = None) -> list[tuple]:
        return self.con.execute(query, list(params) if params else None).fetchall()

    def one(self, query: str, params: Iterable[Any] | None = None) -> Any:
        row = self.con.execute(query, list(params) if params else None).fetchone()
        return row[0] if row else None

    def df(self, query: str, params: Iterable[Any] | None = None):
        """pandas DataFrame result; pandas is imported lazily by DuckDB."""
        return self.con.execute(query, list(params) if params else None).df()

    def _write(self, table: str, columns: list[str], rows: list[dict], *, mode: str) -> int:
        """Explicit-column insert. mode 'replace' upserts by primary key; mode
        'ignore' keeps the existing row and returns how many were actually new."""
        if not rows:
            return 0
        if table in APPEND_ONLY_TABLES and mode != "ignore":
            raise ValueError(f"{table} is append-only")
        placeholders = ", ".join("?" for _ in columns)
        verb = "INSERT OR REPLACE" if mode == "replace" else "INSERT OR IGNORE"
        before = self.one(f"SELECT count(*) FROM {table}")
        self.con.executemany(
            f"{verb} INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            [[row.get(c) for c in columns] for row in rows],
        )
        after = self.one(f"SELECT count(*) FROM {table}")
        return len(rows) if mode == "replace" else int(after - before)

    def count(self, table: str) -> int:
        return int(self.one(f"SELECT count(*) FROM {table}") or 0)

    # ---- tiles (crawl progress) ---------------------------------------------

    def done_tile_ids(self, corridor: str) -> set[str]:
        """Tiles to skip on a rerun. 'split' tiles count too: their children carry
        the real work and are tracked separately. 'error' tiles are retried."""
        return {r[0] for r in self.sql("SELECT tile_id FROM tiles WHERE corridor = ? AND status <> 'error'", [corridor])}

    def upsert_tile(self, corridor: str, tile: BBox, status: str, n_images: int) -> None:
        self._write("tiles", TILE_COLUMNS, [{
            "tile_id": tile.tile_id, "corridor": corridor,
            "min_lon": tile.min_lon, "min_lat": tile.min_lat, "max_lon": tile.max_lon, "max_lat": tile.max_lat,
            "status": status, "n_images": n_images, "fetched_at": _utcnow(),
        }], mode="replace")

    def clear_tiles(self, corridor: str) -> None:
        self.con.execute("DELETE FROM tiles WHERE corridor = ?", [corridor])

    # ---- images -------------------------------------------------------------

    def upsert_images(self, rows: list[dict]) -> int:
        now = _utcnow()
        for row in rows:
            row.setdefault("fetched_at", now)
        return self._write("images", IMAGE_COLUMNS, rows, mode="replace")

    def count_images(self, corridor: str) -> int:
        return int(self.one("SELECT count(*) FROM images WHERE corridor = ?", [corridor]) or 0)

    # ---- downloads ----------------------------------------------------------

    def images_pending_download_v1(self, corridor: str, *, limit: int, max_per_sequence: int = 20, seed: float = 0.42) -> list[dict]:
        """SUPERSEDED 2026-09-05 by images_pending_download(). Kept for comparison.

        Used DuckDB's setseed()+random() for the shuffle. The test that caught
        it: two consecutive calls in one connection returned different orders
        (E-003), so the "400-frame sample" would not have been the same sample
        twice. tests/test_storage.py::test_v2_sampler_is_stable_where_v1_was_not
        keeps the v2 guarantee pinned; v1 is exercised there only to prove it
        still runs, since asserting non-determinism would be flaky by nature.
        """
        self.con.execute("SELECT setseed(?)", [seed])
        rows = self.con.execute(
            """
            WITH candidates AS (
                SELECT i.image_id, i.sequence_id, i.thumb_original_url, i.thumb_2048_url, i.thumb_1024_url,
                       row_number() OVER (PARTITION BY i.sequence_id ORDER BY random()) AS rn_in_seq,
                       random() AS r
                FROM images i
                LEFT JOIN downloads d ON d.image_id = i.image_id AND d.error IS NULL
                WHERE i.corridor = ? AND d.image_id IS NULL AND NOT coalesce(i.is_pano, false)
            )
            SELECT image_id, sequence_id, thumb_original_url, thumb_2048_url, thumb_1024_url
            FROM candidates WHERE rn_in_seq <= ? ORDER BY r LIMIT ?
            """,
            [corridor, max_per_sequence, limit],
        ).fetchall()
        keys = ["image_id", "sequence_id", "thumb_original_url", "thumb_2048_url", "thumb_1024_url"]
        return [dict(zip(keys, r)) for r in rows]

    def images_pending_download(
        self,
        corridor: str,
        *,
        limit: int,
        max_per_sequence: int = 20,
        population: str = "perspective",
        seed: str = "phase0",
    ) -> list[dict]:
        """Pick which indexed images to fetch pixels for.

        Cap per sequence, because consecutive frames are near-duplicates: one
        long drive would otherwise supply 400 photos of the same 4 km and the
        detector would be scored 20 times on the same bison. `population`
        selects perspective frames or panoramas (ADR-0006). The shuffle is
        `hash(image_id || seed)`: same pick on every run and every machine.
        """
        if population not in POPULATION_FILTER:
            raise ValueError(f"population must be one of {list(POPULATION_FILTER)}")
        rows = self.con.execute(
            f"""
            WITH candidates AS (
                SELECT i.image_id, i.sequence_id, i.thumb_original_url, i.thumb_2048_url, i.thumb_1024_url,
                       row_number() OVER (PARTITION BY i.sequence_id ORDER BY hash(i.image_id || ':' || ?)) AS rn_in_seq,
                       hash(i.image_id || ':' || ?) AS r
                FROM images i
                LEFT JOIN downloads d ON d.image_id = i.image_id AND d.error IS NULL
                WHERE i.corridor = ?
                  AND d.image_id IS NULL
                  AND {POPULATION_FILTER[population]}
            )
            SELECT image_id, sequence_id, thumb_original_url, thumb_2048_url, thumb_1024_url
            FROM candidates
            WHERE rn_in_seq <= ?
            ORDER BY r
            LIMIT ?
            """,
            [str(seed), str(seed), corridor, max_per_sequence, limit],
        ).fetchall()
        keys = ["image_id", "sequence_id", "thumb_original_url", "thumb_2048_url", "thumb_1024_url"]
        return [dict(zip(keys, r)) for r in rows]

    def record_download(self, row: dict) -> None:
        row = dict(row)
        row.setdefault("downloaded_at", _utcnow())
        self._write("downloads", DOWNLOAD_COLUMNS, [row], mode="replace")

    def downloaded(self, corridor: str, *, population: str = "perspective") -> list[dict]:
        rows = self.sql(
            f"""
            SELECT d.image_id, d.local_path, i.width, i.height FROM downloads d
            JOIN images i USING (image_id)
            WHERE i.corridor = ? AND d.error IS NULL AND {POPULATION_FILTER[population]}
            """,
            [corridor],
        )
        return [dict(zip(["image_id", "local_path", "width", "height"], r)) for r in rows]

    # ---- model output: append-only -----------------------------------------

    def record_run(self, row: dict) -> None:
        self._write("runs", RUN_COLUMNS, [row], mode="replace")

    def append_predictions(self, rows: list[dict]) -> int:
        """Returns how many rows were new. Existing (image, model, variant) rows
        are left exactly as they were."""
        now = _utcnow()
        for row in rows:
            row.setdefault("predicted_at", now)
            row.setdefault("variant", "full")
        return self._write("predictions_raw", PREDICTION_COLUMNS, rows, mode="ignore")

    def append_detections(self, rows: list[dict]) -> int:
        for row in rows:
            row.setdefault("variant", "full")
        return self._write("detections_raw", DETECTION_COLUMNS, rows, mode="ignore")

    # ---- human review -------------------------------------------------------

    def upsert_reviews(self, rows: list[dict]) -> int:
        now = _utcnow()
        for row in rows:
            row.setdefault("reviewed_at", now)
            row.setdefault("variant", "full")
        return self._write("manual_review", REVIEW_COLUMNS, rows, mode="replace")

    # ---- sightings (Track A now, Track B later) -----------------------------

    def upsert_sightings(self, rows: list[dict]) -> int:
        """Reference data is a mirror of the source and may be refreshed; that is
        not model output, so replace is correct here."""
        now = _utcnow()
        for row in rows:
            row.setdefault("fetched_at", now)
        return self._write("sightings", SIGHTING_COLUMNS, rows, mode="replace")

    def mark_duplicates(self, pairs: list[tuple[str, str]]) -> int:
        """pairs of (duplicate_sighting_id, canonical_sighting_id)."""
        if not pairs:
            return 0
        self.con.executemany("UPDATE sightings SET duplicate_of = ? WHERE sighting_id = ?", [[c, d] for d, c in pairs])
        return len(pairs)

    def clear_duplicates(self, park: str) -> None:
        self.con.execute("UPDATE sightings SET duplicate_of = NULL WHERE park = ?", [park])
