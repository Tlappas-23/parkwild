"""Fetch pixels for a sample of indexed images.

PROBLEM: the index holds URLs, not images, and resolution is the binding
constraint on detection range: a bison 300 m away is a handful of pixels at
1024 px wide.

FIRST ATTEMPT: an `exclude_pano` boolean, because the first plan sampled
perspective frames only. Replaced by a `population` name once the build spec
required both populations measured separately (ADR-0006); the selection
itself lives in storage.images_pending_download.

CURRENT: default to `thumb_original_url`, fall back to 2048 then 1024; a
small thread pool for HTTP with all DuckDB writes on the main thread (a
DuckDB connection must not be shared across threads); verify every file with
PIL before keeping it, because a truncated JPEG would crash the detector
halfway through a batch; on 403 re-fetch the image entity for a fresh signed
URL and retry once. 400 of 400 Lamar frames succeeded, 749 MB.

UNRESOLVED: how long Mapillary's signed thumbnail URLs live. Nothing expired
within the hour between index and download; the refresh path is untested
against a real expiry.
"""
from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import requests
from PIL import Image
from tqdm import tqdm

from .decisionlog import record_sample
from .mapillary import MapillaryClient
from .storage import Store

log = logging.getLogger(__name__)

# SIZE_PREFERENCE — DERIVED (from the three thumbnail fields the API offers)
# Largest first: `thumb_original_url` was present on all 27,430 Lamar images,
# so the fallbacks have not been exercised. Original files averaged 3789 x
# 2843 px and 1.9 MB.
# REVISIT IF: a corridor's originals are huge (>10 MB) and 2048 would do.
SIZE_PREFERENCE = {
    "original": ("thumb_original_url", "thumb_2048_url", "thumb_1024_url"),
    "2048": ("thumb_2048_url", "thumb_1024_url"),
    "1024": ("thumb_1024_url",),
}
THUMB_FIELDS = ("id", "thumb_original_url", "thumb_2048_url", "thumb_1024_url")


@dataclass
class DownloadResult:
    image_id: str
    local_path: str | None = None
    size_kind: str | None = None
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    sha256: str | None = None
    error: str | None = None


def _pick_url(row: dict, size: str) -> tuple[str | None, str | None]:
    """First non-empty URL for the requested size, with its kind ('original', ...)."""
    for field_name in SIZE_PREFERENCE[size]:
        url = row.get(field_name)
        if url:
            return field_name.replace("thumb_", "").replace("_url", ""), url
    return None, None


def _verify_image(path: Path) -> tuple[int, int]:
    """Make sure the file is a real, complete image and return (width, height).
    PIL's verify() catches truncated downloads that would otherwise crash the
    detector halfway through a batch."""
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        return im.size


def fetch_one(
    row: dict,
    *,
    out_dir: Path,
    size: str,
    client: MapillaryClient,
    session: requests.Session,
    timeout_s: float = 120,
) -> DownloadResult:
    """Download one image to out_dir/<image_id>.jpg. Idempotent: an existing,
    valid file is a cache hit and no request is made."""
    image_id = row["image_id"]
    dest = out_dir / f"{image_id}.jpg"
    tmp = out_dir / f"{image_id}.part"

    if dest.exists():
        try:
            w, h = _verify_image(dest)
            data = dest.read_bytes()
            return DownloadResult(image_id, str(dest), "cached", w, h, len(data), hashlib.sha256(data).hexdigest())
        except Exception:  # corrupt partial file from an earlier run: redo it
            dest.unlink(missing_ok=True)

    kind, url = _pick_url(row, size)
    if not url:
        return DownloadResult(image_id, error=f"no thumbnail URL for size={size}")

    for attempt in (1, 2):
        try:
            resp = session.get(url, stream=True, timeout=timeout_s)
        except requests.RequestException as exc:
            return DownloadResult(image_id, error=f"request failed: {exc}")
        if resp.status_code == 200:
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
            break
        if resp.status_code in (403, 404, 410) and attempt == 1:
            # Signed URL probably expired. Ask the API for a fresh one.
            try:
                fresh = client.get_image(image_id, fields=THUMB_FIELDS)
            except Exception as exc:
                return DownloadResult(image_id, error=f"refresh failed: {exc}")
            kind, url = _pick_url(fresh, size)
            if not url:
                return DownloadResult(image_id, error="no thumbnail URL after refresh")
            continue
        return DownloadResult(image_id, error=f"HTTP {resp.status_code}")
    else:
        return DownloadResult(image_id, error="download failed after URL refresh")

    try:
        w, h = _verify_image(tmp)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        return DownloadResult(image_id, error=f"invalid image: {exc}")
    data = tmp.read_bytes()
    tmp.rename(dest)
    return DownloadResult(image_id, str(dest), kind, w, h, len(data), hashlib.sha256(data).hexdigest())


def download_images(
    store: Store,
    client: MapillaryClient,
    corridor: str,
    *,
    out_dir: Path,
    size: str = "original",
    limit: int = 400,
    max_per_sequence: int = 20,
    population: str = "perspective",
    workers: int = 4,
) -> dict[str, int]:
    """Download up to `limit` not-yet-fetched images of one population
    (perspective frames or panoramas) for a corridor and record each outcome,
    success or error, in the `downloads` table."""
    if size not in SIZE_PREFERENCE:
        raise ValueError(f"size must be one of {list(SIZE_PREFERENCE)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = store.images_pending_download(
        corridor, limit=limit, max_per_sequence=max_per_sequence, population=population
    )
    log.info("%d %s images to download for %s (size=%s)", len(rows), population, corridor, size)
    record_sample(f"{corridor}_{population}_download", [r["image_id"] for r in rows],
                  seed="phase0", limit=limit, max_per_sequence=max_per_sequence, size=size)

    session = requests.Session()
    ok = failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(fetch_one, row, out_dir=out_dir, size=size, client=client, session=session)
            for row in rows
        ]
        for future in tqdm(as_completed(futures), total=len(futures), unit="img", desc="download"):
            result = future.result()
            store.record_download(asdict(result))
            if result.error:
                failed += 1
                log.warning("%s: %s", result.image_id, result.error)
            else:
                ok += 1
    return {"requested": len(rows), "ok": ok, "failed": failed}
