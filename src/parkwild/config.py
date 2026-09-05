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
from dataclasses import dataclass, field
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
SUPPRESSION_TOML = ROOT / "config" / "suppression.toml"
TAXONOMY_TOML = ROOT / "config" / "taxonomy.toml"
EXPORT_DIR = DATA_DIR / "export"          # data/export/<park>/{cells.geojson,species.json,sightings.parquet,manifest.json}
RESULTS_MD = ROOT / "RESULTS.md"

# MAPILLARY_LICENSE — BORROWED (Mapillary terms of service, section 3(b), read 2026-09-05)
# Stored on every image row. Section 11 additionally asks for the Mapillary
# logo and a link back on anything published; that is the app's job.
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
    # The virtual tour: stop names in visiting order, matched to OpenStreetMap
    # features by parkwild.landmarks; tour_fallback gives a coordinate for a
    # stop OSM has no named feature for (valleys, mostly).
    tour: tuple[str, ...] = ()
    tour_fallback: dict[str, tuple[float, float]] = field(default_factory=dict)
    # "<stop>@wiki" = article title, for stops whose OSM feature has no wikipedia
    # tag or whose bare name is a disambiguation page ("Lower Falls").
    tour_wiki: dict[str, str] = field(default_factory=dict)


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
            tour=tuple(section.get("tour", ())),
            tour_fallback={k: (float(v[0]), float(v[1])) for k, v in section.get("tour_fallback", {}).items() if not k.endswith("@wiki")},
            tour_wiki={k[:-5]: str(v) for k, v in section.get("tour_fallback", {}).items() if k.endswith("@wiki")},
        )
        for key, section in raw.items()
    }


def get_park(key: str) -> Park:
    parks = load_parks()
    if key not in parks:
        raise KeyError(f"unknown park {key!r}; known: {', '.join(parks)}")
    return parks[key]


@dataclass(frozen=True)
class Suppression:
    name: str          # scientific-name prefix
    common: str
    action: str        # exclude | coarsen
    res: int | None    # H3 resolution when coarsening
    why: str


def load_suppression(path: Path = SUPPRESSION_TOML) -> list[Suppression]:
    """The species suppression list. Every entry carries its own reason, so the
    choice is visible and revisable rather than buried in export code."""
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    out = []
    for e in raw.get("species", []):
        if e["action"] not in ("exclude", "coarsen"):
            raise ValueError(f"suppression {e['name']}: action must be exclude or coarsen")
        if e["action"] == "coarsen" and "res" not in e:
            raise ValueError(f"suppression {e['name']}: coarsen needs res")
        out.append(Suppression(e["name"], e.get("common", ""), e["action"], e.get("res"), e.get("why", "")))
    return out


def load_synonyms(path: Path = TAXONOMY_TOML) -> dict[str, str]:
    """GBIF-backbone -> iNaturalist spellings for the same animal (config/taxonomy.toml)."""
    with open(path, "rb") as fh:
        return dict(tomllib.load(fh).get("synonyms", {}))


def canonical_species(name: str | None, synonyms: dict[str, str]) -> str | None:
    """Collapse a subspecies to its species (first two words) and apply the
    synonym table. 'Bos bison bison' -> 'Bos bison' -> 'Bison bison'."""
    if not name:
        return None
    parts = name.split()
    base = " ".join(parts[:2]) if len(parts) >= 3 and parts[0][:1].isupper() and parts[1].islower() else name
    return synonyms.get(base, base)
