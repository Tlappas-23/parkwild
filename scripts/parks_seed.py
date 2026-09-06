"""Look up every US national park on iNaturalist and write the config stanzas.

    scripts/parks_seed.py                # writes config/parks.seed.toml, prints what it could not match
    scripts/parks_seed.py --only "Zion,Acadia"

The 63 parks are listed here by name and state. For each, iNaturalist's
place search is asked for "<name> National Park"; the first result whose
name is exactly that (case-insensitive) is taken, and its bounding box is
sanity-checked (a park is not 20 degrees wide). Anything else is printed
for a person to resolve. The output file is a *seed*: copy stanzas into
config/parks.toml after a glance, and add a `tour` list when you know the
park; without one the landmarks step picks stops automatically.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parkwild.inaturalist import find_places  # noqa: E402

# PARKS — BORROWED (the National Park Service's list of the 63 designated
# national parks, 2024; the state is the primary one)
PARKS: list[tuple[str, str]] = [
    ("Acadia", "ME"), ("American Samoa", "AS"), ("Arches", "UT"), ("Badlands", "SD"), ("Big Bend", "TX"),
    ("Biscayne", "FL"), ("Black Canyon of the Gunnison", "CO"), ("Bryce Canyon", "UT"), ("Canyonlands", "UT"),
    ("Capitol Reef", "UT"), ("Carlsbad Caverns", "NM"), ("Channel Islands", "CA"), ("Congaree", "SC"),
    ("Crater Lake", "OR"), ("Cuyahoga Valley", "OH"), ("Death Valley", "CA"), ("Denali", "AK"), ("Dry Tortugas", "FL"),
    ("Everglades", "FL"), ("Gates of the Arctic", "AK"), ("Gateway Arch", "MO"), ("Glacier", "MT"), ("Glacier Bay", "AK"),
    ("Grand Canyon", "AZ"), ("Grand Teton", "WY"), ("Great Basin", "NV"), ("Great Sand Dunes", "CO"),
    ("Great Smoky Mountains", "TN"), ("Guadalupe Mountains", "TX"), ("Haleakalā", "HI"), ("Hawaiʻi Volcanoes", "HI"),
    ("Hot Springs", "AR"), ("Indiana Dunes", "IN"), ("Isle Royale", "MI"), ("Joshua Tree", "CA"), ("Katmai", "AK"),
    ("Kenai Fjords", "AK"), ("Kings Canyon", "CA"), ("Kobuk Valley", "AK"), ("Lake Clark", "AK"), ("Lassen Volcanic", "CA"),
    ("Mammoth Cave", "KY"), ("Mesa Verde", "CO"), ("Mount Rainier", "WA"), ("New River Gorge", "WV"),
    ("North Cascades", "WA"), ("Olympic", "WA"), ("Petrified Forest", "AZ"), ("Pinnacles", "CA"), ("Redwood", "CA"),
    ("Rocky Mountain", "CO"), ("Saguaro", "AZ"), ("Sequoia", "CA"), ("Shenandoah", "VA"), ("Theodore Roosevelt", "ND"),
    ("Virgin Islands", "VI"), ("Voyageurs", "MN"), ("White Sands", "NM"), ("Wind Cave", "SD"), ("Wrangell-St. Elias", "AK"),
    ("Yellowstone", "WY"), ("Yosemite", "CA"), ("Zion", "UT"),
]

# MAX_BBOX_DEG — ASSUMED (Wrangell-St. Elias, the largest, spans about 5 degrees;
# anything wider is a state or a country that happened to share the name)
MAX_BBOX_DEG = 8.0


def key_of(name: str) -> str:
    import re
    import unicodedata
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")


def bbox_of(place: dict) -> list[float] | None:
    """find_places already reduces iNaturalist's bounding_box_geojson to [w, s, e, n]."""
    bb = place.get("bbox")
    return [round(v, 6) for v in bb] if bb and None not in bb else None


# ALIASES — MEASURED (the four parks whose iNaturalist place is not called
# "<name> National Park", found by the first seed run on 2026-09-05)
ALIASES = {
    "American Samoa": "National Park of American Samoa",
    "Haleakalā": "Haleakala National Park",
    "Hawaiʻi Volcanoes": "Hawaii Volcanoes National Park",
    "Indiana Dunes": "Indiana Dunes National Park",
}


def lookup(name: str) -> tuple[dict | None, list[str]]:
    wanted = ALIASES.get(name, f"{name} National Park").casefold()
    # "Redwood National and State Parks", "Sequoia and Kings Canyon" and the
    # Hawaiian names do not follow the pattern; take the exact name first,
    # then any result that starts with the park's name and says "national park".
    results = find_places(ALIASES.get(name, f"{name} National Park"))
    if not results and name in ALIASES:
        results = find_places(name)
    exact = [p for p in results if (p.get("name") or "").casefold().split(",")[0] == wanted]
    loose = [p for p in results if (p.get("name") or "").casefold().startswith(name.casefold()) and "national" in (p.get("name") or "").casefold()]
    for cand in exact + loose:
        bb = bbox_of(cand)
        if bb and (bb[2] - bb[0]) < MAX_BBOX_DEG and (bb[3] - bb[1]) < MAX_BBOX_DEG:
            return cand, []
    return None, [f'{p.get("id")}: {p.get("name")}' for p in results[:5]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated park names to look up")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "config" / "parks.seed.toml"))
    args = ap.parse_args(argv)
    only = {n.strip().casefold() for n in args.only.split(",")} if args.only else None
    stanzas, unmatched = [], []
    for name, state in PARKS:
        if only and name.casefold() not in only:
            continue
        place, alternatives = lookup(name)
        time.sleep(1.0)     # iNaturalist etiquette
        if place is None:
            unmatched.append((name, alternatives))
            continue
        stanzas.append(
            f"[{key_of(name)}]\nname          = {json.dumps((place.get('name') or name).split(',')[0])}\n"
            f"state         = \"{state}\"\ninat_place_id = {place['id']}\nbbox          = {json.dumps(bbox_of(place))}\n"
        )
        print(f"ok  {name:32s} place {place['id']:>7}  {place.get('name')}")
    Path(args.out).write_text("# Seed stanzas from scripts/parks_seed.py; copy into parks.toml after a glance.\n\n" + "\n".join(stanzas))
    for name, alternatives in unmatched:
        print(f"??  {name}: no exact match; candidates: {alternatives}")
    print(f"{len(stanzas)} matched, {len(unmatched)} to resolve -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
