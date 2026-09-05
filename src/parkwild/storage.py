"""
DuckDB persistence. One file, a handful of tables, no ORM.

Rules I'm following from the project brief:

- `images` is the crawl index: one row per Mapillary image keyed by image ID, and
  the attribution columns (image_id, creator_username, license, source_url) are
  always populated.
- `tiles` is crawl progress, so a rerun resumes instead of restarting.
- `predictions_raw` / `detections_raw` hold model output exactly as SpeciesNet
  emitted it, keyed by (image_id, model_version). Nothing updates those rows.
  Human corrections go to `manual_review`, so accuracy can be recomputed later
  against the untouched raw output.

DuckDB's `INSERT OR REPLACE` does the upsert-by-primary-key work; that's why
every table declares one.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

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
    camera_type            VARCHAR,          -- perspective | fisheye | equirectangular
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
    status     VARCHAR,     -- done | split | capped
    n_images   INTEGER,
    fetched_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS downloads (
    image_id      VARCHAR PRIMARY KEY,
    local_path    VARCHAR,
    size_kind     VARCHAR,   -- original | 2048 | 1024
    width         INTEGER,
    height        INTEGER,
    bytes         BIGINT,
    sha256        VARCHAR,
    error         VARCHAR,   -- NULL on success
    downloaded_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS predictions_raw (
    image_id          VARCHAR,
    model_version     VARCHAR,
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
    PRIMARY KEY (image_id, model_version)
);

CREATE TABLE IF NOT EXISTS detections_raw (
    image_id      VARCHAR,
    model_version VARCHAR,
    det_idx       INTEGER,
    category      VARCHAR,   -- '1' animal, '2' human, '3' vehicle
    label         VARCHAR,
    conf          DOUBLE,
    bbox_x        DOUBLE,    -- normalised [0,1]: x_min, y_min, width, height
    bbox_y        DOUBLE,
    bbox_w        DOUBLE,
    bbox_h        DOUBLE,
    PRIMARY KEY (image_id, model_version, det_idx)
);

CREATE TABLE IF NOT EXISTS manual_review (
    image_id       VARCHAR,
    det_idx        INTEGER,
    reviewer       VARCHAR,
    verdict        VARCHAR,   -- tp | fp | unsure
    true_species   VARCHAR,   -- what I think it is, free text
    species_agree  VARCHAR,   -- yes | rollup | no | na
    est_distance_m DOUBLE,
    notes          VARCHAR,
    reviewed_at    TIMESTAMP,
    PRIMARY KEY (image_id, det_idx, reviewer)
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
PREDICTION_COLUMNS = [
    "image_id", "model_version", "run_id", "prediction", "prediction_score",
    "prediction_source", "top5_classes", "top5_scores", "n_detections",
    "max_animal_conf", "failures", "raw_json", "predicted_at",
]
DETECTION_COLUMNS = [
    "image_id", "model_version", "det_idx", "category", "label", "conf",
    "bbox_x", "bbox_y", "bbox_w", "bbox_h",
]
REVIEW_COLUMNS = [
    "image_id", "det_idx", "reviewer", "verdict", "true_species", "species_agree",
    "est_distance_m", "notes", "reviewed_at",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Store:
    def __init__(self, path: Path | str = DB_PATH, *, read_only: bool = False) -> None:
        path = str(path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(path, read_only=read_only)
        if not read_only:
            self.con.execute(SCHEMA)

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "Store":
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
        """pandas DataFrame result. pandas is only in the dev extras, so it is
        imported lazily here rather than at module load."""
        return self.con.execute(query, list(params) if params else None).df()

    def _upsert(self, table: str, columns: list[str], rows: list[dict]) -> int:
        if not rows:
            return 0
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        self.con.executemany(sql, [[row.get(c) for c in columns] for row in rows])
        return len(rows)

    # ---- tiles (crawl progress) ---------------------------------------------

    def done_tile_ids(self, corridor: str) -> set[str]:
        """Tiles I can skip on a rerun. 'split' tiles count too: their children
        carry the real work and are tracked separately."""
        return {r[0] for r in self.sql("SELECT tile_id FROM tiles WHERE corridor = ?", [corridor])}

    def upsert_tile(self, corridor: str, tile: BBox, status: str, n_images: int) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO tiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [tile.tile_id, corridor, tile.min_lon, tile.min_lat, tile.max_lon, tile.max_lat,
             status, n_images, _utcnow()],
        )

    def clear_tiles(self, corridor: str) -> None:
        self.con.execute("DELETE FROM tiles WHERE corridor = ?", [corridor])

    # ---- images -------------------------------------------------------------

    def upsert_images(self, rows: list[dict]) -> int:
        now = _utcnow()
        for row in rows:
            row.setdefault("fetched_at", now)
        return self._upsert("images", IMAGE_COLUMNS, rows)

    def count_images(self, corridor: str) -> int:
        return int(self.one("SELECT count(*) FROM images WHERE corridor = ?", [corridor]) or 0)

    # ---- downloads ----------------------------------------------------------

    def images_pending_download(
        self,
        corridor: str,
        *,
        limit: int,
        max_per_sequence: int = 20,
        exclude_pano: bool = True,
        seed: str = "phase0",
    ) -> list[dict]:
        """Pick which indexed images to fetch pixels for.

        Consecutive frames in one sequence are near-duplicates, so a naive random
        sample of a corridor with one long drive in it would be 400 photos of the
        same 4 km. Capping per sequence spreads the sample across contributors and
        dates.

        "Random" here is `hash(image_id || seed)`, not DuckDB's random(): the hash
        is a deterministic shuffle that gives the same pick on every run and every
        machine, whereas setseed()+random() turned out not to be stable across calls.
        """
        rows = self.con.execute(
            """
            WITH candidates AS (
                SELECT i.image_id, i.sequence_id, i.thumb_original_url, i.thumb_2048_url, i.thumb_1024_url,
                       row_number() OVER (PARTITION BY i.sequence_id ORDER BY hash(i.image_id || ':' || ?)) AS rn_in_seq,
                       hash(i.image_id || ':' || ?) AS r
                FROM images i
                LEFT JOIN downloads d ON d.image_id = i.image_id AND d.error IS NULL
                WHERE i.corridor = ?
                  AND d.image_id IS NULL
                  AND (NOT ? OR NOT coalesce(i.is_pano, false))
            )
            SELECT image_id, sequence_id, thumb_original_url, thumb_2048_url, thumb_1024_url
            FROM candidates
            WHERE rn_in_seq <= ?
            ORDER BY r
            LIMIT ?
            """,
            [str(seed), str(seed), corridor, exclude_pano, max_per_sequence, limit],
        ).fetchall()
        keys = ["image_id", "sequence_id", "thumb_original_url", "thumb_2048_url", "thumb_1024_url"]
        return [dict(zip(keys, r)) for r in rows]

    def record_download(self, row: dict) -> None:
        row = dict(row)
        row.setdefault("downloaded_at", _utcnow())
        self._upsert(
            "downloads",
            ["image_id", "local_path", "size_kind", "width", "height", "bytes", "sha256", "error", "downloaded_at"],
            [row],
        )

    def downloaded_paths(self, corridor: str) -> list[tuple[str, str]]:
        return self.sql(
            """
            SELECT d.image_id, d.local_path FROM downloads d
            JOIN images i USING (image_id)
            WHERE i.corridor = ? AND d.error IS NULL
            """,
            [corridor],
        )

    # ---- model output (append-only in spirit) -------------------------------

    def upsert_predictions(self, rows: list[dict]) -> int:
        now = _utcnow()
        for row in rows:
            row.setdefault("predicted_at", now)
        return self._upsert("predictions_raw", PREDICTION_COLUMNS, rows)

    def upsert_detections(self, rows: list[dict]) -> int:
        return self._upsert("detections_raw", DETECTION_COLUMNS, rows)

    # ---- human review -------------------------------------------------------

    def upsert_reviews(self, rows: list[dict]) -> int:
        now = _utcnow()
        for row in rows:
            row.setdefault("reviewed_at", now)
        return self._upsert("manual_review", REVIEW_COLUMNS, rows)
