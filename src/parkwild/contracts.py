"""
Stage-boundary contracts.

Cheap assertions that catch the classic silent failures: a swapped lat/lon, a
timestamp in seconds where milliseconds were expected, a bounding box in pixels
where normalised was expected, rows lost between two stages. They raise
ContractError with the offending value so the failure is loud and specific.
"""
from __future__ import annotations

from collections.abc import Iterable


class ContractError(AssertionError):
    pass


def check_lon_lat(rows: Iterable[dict], *, lon_key: str = "lon", lat_key: str = "lat", allow_none: bool = True) -> int:
    """Longitude in [-180, 180], latitude in [-90, 90]. A latitude over 90 is
    almost always a swapped pair. Returns the number of rows checked."""
    n = 0
    for row in rows:
        lon, lat = row.get(lon_key), row.get(lat_key)
        if lon is None or lat is None:
            if allow_none:
                continue
            raise ContractError(f"missing coordinates in {row.get('image_id') or row.get('sighting_id') or row}")
        if not (-180 <= lon <= 180):
            raise ContractError(f"longitude out of range: {lon} (row {row.get('image_id') or row.get('sighting_id')})")
        if not (-90 <= lat <= 90):
            raise ContractError(f"latitude out of range: {lat} (row {row.get('image_id') or row.get('sighting_id')})")
        n += 1
    return n


def check_bbox_normalized(rows: Iterable[dict], *, eps: float = 1e-6) -> int:
    """SpeciesNet boxes are (x_min, y_min, w, h) in [0, 1]. Anything above 1 means
    pixels leaked in; a negative width means a corner-format box."""
    n = 0
    for row in rows:
        x, y, w, h = row.get("bbox_x"), row.get("bbox_y"), row.get("bbox_w"), row.get("bbox_h")
        if None in (x, y, w, h):
            continue
        if not (0 - eps <= x <= 1 + eps and 0 - eps <= y <= 1 + eps):
            raise ContractError(f"bbox origin out of [0,1]: ({x}, {y}) in {row.get('image_id')}")
        if not (0 <= w <= 1 + eps and 0 <= h <= 1 + eps):
            raise ContractError(f"bbox size out of [0,1]: ({w}, {h}) in {row.get('image_id')}")
        if x + w > 1 + 1e-3 or y + h > 1 + 1e-3:
            raise ContractError(f"bbox extends past the frame: x+w={x + w:.4f}, y+h={y + h:.4f} in {row.get('image_id')}")
        n += 1
    return n


def check_ms_epoch(values: Iterable[int | None]) -> int:
    """Mapillary's captured_at is milliseconds. Seconds (1.7e9) or microseconds
    (1.7e15) both fail this: the window is roughly 2001 to 2033 in ms."""
    n = 0
    for v in values:
        if v is None:
            continue
        if not (1_000_000_000_000 <= v < 2_000_000_000_000):
            raise ContractError(f"captured_at {v} is not a millisecond epoch")
        n += 1
    return n


def check_conservation(n_in: int, n_kept: int, n_dropped: int, *, stage: str = "") -> None:
    if n_in != n_kept + n_dropped:
        raise ContractError(f"{stage}: {n_in} in != {n_kept} kept + {n_dropped} dropped")
