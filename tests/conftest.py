"""Shared fixtures. Everything runs offline against an in-memory DuckDB."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Keep test runs out of the real decision ledger (E-020). Set before parkwild
# is imported anywhere; decisionlog.default_log_path reads it at call time.
os.environ["PARKWILD_DECISION_LOG"] = os.path.join(tempfile.mkdtemp(prefix="parkwild-tests-"), "decision_log.jsonl")

from parkwild.storage import Store

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def store() -> Store:
    s = Store(":memory:")
    yield s
    s.close()


def image_row(image_id: str, *, sequence: str = "seq-a", corridor: str = "test", is_pano: bool = False,
              captured_at_ms: int = 1_700_000_000_000, lon: float = -110.2, lat: float = 44.9, **extra) -> dict:
    """A minimal valid `images` row."""
    row = {
        "image_id": image_id,
        "corridor": corridor,
        "lon": lon, "lat": lat, "lon_raw": lon, "lat_raw": lat, "position_source": "gps",
        "captured_at_ms": captured_at_ms, "captured_at": datetime.fromtimestamp(captured_at_ms / 1000, tz=UTC).replace(tzinfo=None),
        "compass_angle": 90.0, "computed_compass_angle": None,
        "camera_type": "spherical" if is_pano else "perspective", "is_pano": is_pano, "make": None, "model": None,
        "width": 4096 if is_pano else 4000, "height": 2048 if is_pano else 3000, "quality_score": None,
        "sequence_id": sequence, "creator_id": "1", "creator_username": "alice",
        "license": "CC BY-SA 4.0", "source_url": f"https://www.mapillary.com/app/?pKey={image_id}",
        "thumb_1024_url": "https://x/1024", "thumb_2048_url": "https://x/2048", "thumb_original_url": "https://x/orig",
        "mapillary_detections": None, "raw_json": "{}",
    }
    row.update(extra)
    return row


def speciesnet_payload() -> dict:
    return json.loads((FIXTURES / "speciesnet_predictions.json").read_text())


def write_payload(tmp_path) -> Path:
    p = tmp_path / "preds.json"
    p.write_text(json.dumps(speciesnet_payload()))
    return p


def inat_observations() -> list[dict]:
    return json.loads((FIXTURES / "inat_observations.json").read_text())


def gbif_occurrences() -> list[dict]:
    return json.loads((FIXTURES / "gbif_occurrences.json").read_text())


def seed_phase0(store: Store, tmp_path) -> None:
    """images + downloads + parsed fixture predictions for corridor 'test'.
    img1..img5 are perspective frames (img1/img4/img5 in one sequence, seconds
    apart); pano1 is a panorama with one slice scored."""
    from parkwild.speciesnet_runner import parse_predictions

    store.upsert_images([
        image_row("img1"), image_row("img2", sequence="s2"), image_row("img3", sequence="s3"),
        image_row("img4", sequence="seq-a", captured_at_ms=1_700_000_005_000, lon=-110.2003, lat=44.9001),
        image_row("img5", sequence="seq-a", captured_at_ms=1_700_000_008_000, lon=-110.2005, lat=44.9002),
        image_row("pano1", sequence="p1", is_pano=True),
    ])
    for i in ("img1", "img2", "img3", "img4", "img5", "pano1"):
        store.record_download({"image_id": i, "local_path": f"/x/{i}.jpg", "size_kind": "original", "error": None})
    preds, dets = parse_predictions(write_payload(tmp_path), run_id="r1")
    store.append_predictions(preds)
    store.append_detections(dets)
