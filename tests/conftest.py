"""Shared fixtures. Everything runs offline against an in-memory DuckDB."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from parkwild.storage import Store


@pytest.fixture
def store() -> Store:
    s = Store(":memory:")
    yield s
    s.close()


def image_row(image_id: str, *, sequence: str = "seq-a", corridor: str = "test", is_pano: bool = False, **extra) -> dict:
    """A minimal valid `images` row."""
    row = {
        "image_id": image_id,
        "corridor": corridor,
        "lon": -110.2, "lat": 44.9, "lon_raw": -110.2, "lat_raw": 44.9, "position_source": "gps",
        "captured_at_ms": 1_700_000_000_000, "captured_at": datetime(2023, 11, 14, 22, 13, 20),
        "compass_angle": 90.0, "computed_compass_angle": None,
        "camera_type": "perspective", "is_pano": is_pano, "make": None, "model": None,
        "width": 4000, "height": 3000, "quality_score": None,
        "sequence_id": sequence, "creator_id": "1", "creator_username": "alice",
        "license": "CC BY-SA 4.0", "source_url": f"https://www.mapillary.com/app/?pKey={image_id}",
        "thumb_1024_url": "https://x/1024", "thumb_2048_url": "https://x/2048", "thumb_original_url": "https://x/orig",
        "mapillary_detections": None, "raw_json": "{}",
    }
    row.update(extra)
    return row


def speciesnet_payload() -> dict:
    """A realistic slice of SpeciesNet output: one bison, one blank, one failure."""
    bison = "a1b2;mammalia;cetartiodactyla;bovidae;bison;bison;american bison"
    deer_family = "c3d4;mammalia;cetartiodactyla;cervidae;;;deer family"
    return {
        "predictions": [
            {
                "filepath": "/data/images/test/img1.jpg",
                "classifications": {"classes": [bison, deer_family], "scores": [0.91, 0.05]},
                "detections": [
                    {"category": "1", "label": "animal", "conf": 0.88, "bbox": [0.40, 0.50, 0.05, 0.03]},
                    {"category": "1", "label": "animal", "conf": 0.15, "bbox": [0.10, 0.55, 0.02, 0.02]},
                    {"category": "3", "label": "vehicle", "conf": 0.95, "bbox": [0.60, 0.60, 0.20, 0.15]},
                ],
                "prediction": bison, "prediction_score": 0.91, "prediction_source": "classifier",
                "model_version": "4.0.3a",
            },
            {
                "filepath": "/data/images/test/img2.jpg",
                "classifications": {"classes": ["blank"], "scores": [0.99]},
                "detections": [],
                "prediction": "blank", "prediction_score": 0.99, "prediction_source": "classifier",
                "model_version": "4.0.3a",
            },
            {
                "filepath": "/data/images/test/img3.jpg",
                "failures": ["CLASSIFIER", "DETECTOR"],
                "model_version": "4.0.3a",
            },
        ]
    }


def write_payload(tmp_path) -> "Path":  # noqa: F821
    p = tmp_path / "preds.json"
    p.write_text(json.dumps(speciesnet_payload()))
    return p
