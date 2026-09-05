"""
Project-wide settings: where things live on disk, how I get the Mapillary token,
and the corridor definitions from config/corridors.toml.

The token is read from the environment first and then from a .env file at the
repo root. I parse that file by hand because it is four lines of work and not
worth a dependency.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .geo import BBox

# Everything is addressed relative to the repo root so the scripts work no matter
# which directory I run them from.
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
IMAGES_DIR = DATA_DIR / "images"          # data/images/<corridor>/<image_id>.jpg
PREDICTIONS_DIR = DATA_DIR / "predictions"  # data/predictions/<corridor>.json (SpeciesNet output)
REVIEW_DIR = DATA_DIR / "review"          # data/review/<corridor>/  gallery + review.csv
DB_PATH = DATA_DIR / "parkwild.duckdb"
CORRIDORS_TOML = ROOT / "config" / "corridors.toml"
PARKS_TOML = ROOT / "config" / "parks.toml"
EXPORT_DIR = DATA_DIR / "export"          # data/export/<park>/{cells.geojson,species.json,sightings.parquet,manifest.json}
RESULTS_MD = ROOT / "RESULTS.md"

# Every Mapillary record I store carries this. Terms of service section 3(b):
# user-contributed imagery is CC BY-SA 4.0; section 11 additionally asks for the
# Mapillary logo and a link back on anything published.
MAPILLARY_LICENSE = "CC BY-SA 4.0"


def load_dotenv(path: Path = ROOT / ".env") -> dict[str, str]:
    """Read KEY=VALUE lines from a .env file. Ignores blanks and # comments,
    strips matching quotes. Returns {} if the file doesn't exist."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def mapillary_token() -> str:
    """Return the Mapillary client token or raise with instructions.

    Environment wins over .env so I can override per shell without editing files."""
    token = os.environ.get("MAPILLARY_TOKEN") or load_dotenv().get("MAPILLARY_TOKEN", "")
    token = token.strip()
    if not token:
        raise RuntimeError(
            "No Mapillary token. Copy .env.example to .env and set MAPILLARY_TOKEN "
            "(free client token from https://www.mapillary.com/dashboard/developers)."
        )
    return token


@dataclass(frozen=True)
class Corridor:
    key: str
    name: str
    park: str
    state: str
    bbox: BBox
    road: str = ""
    notes: str = ""


def load_corridors(path: Path = CORRIDORS_TOML) -> dict[str, Corridor]:
    """Parse config/corridors.toml into Corridor objects, keyed by table name.
    The bbox is validated on construction, so a typo in the TOML fails here and
    not three network calls later."""
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    corridors: dict[str, Corridor] = {}
    for key, section in raw.items():
        corridors[key] = Corridor(
            key=key,
            name=section["name"],
            park=section["park"],
            state=section["state"],
            bbox=BBox.from_list(section["bbox"]),
            road=section.get("road", ""),
            notes=section.get("notes", ""),
        )
    return corridors


def get_corridor(key: str) -> Corridor:
    corridors = load_corridors()
    if key not in corridors:
        raise KeyError(f"unknown corridor {key!r}; known: {', '.join(corridors)}")
    return corridors[key]


@dataclass(frozen=True)
class Park:
    key: str
    name: str
    state: str
    inat_place_id: int
    bbox: BBox
    corridors: tuple[str, ...] = ()


def load_parks(path: Path = PARKS_TOML) -> dict[str, Park]:
    """Parse config/parks.toml. iNaturalist place ids were looked up live and
    are the exact park boundary on that side; the bbox is for GBIF."""
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    return {
        key: Park(
            key=key,
            name=section["name"],
            state=section["state"],
            inat_place_id=int(section["inat_place_id"]),
            bbox=BBox.from_list(section["bbox"]),
            corridors=tuple(section.get("corridors", ())),
        )
        for key, section in raw.items()
    }


def get_park(key: str) -> Park:
    parks = load_parks()
    if key not in parks:
        raise KeyError(f"unknown park {key!r}; known: {', '.join(parks)}")
    return parks[key]
