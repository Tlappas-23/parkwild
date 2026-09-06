"""One index of every park the config knows, for the app's home page.

PROBLEM: switching parks from a dropdown says nothing about what is behind
each name; the owner wants a home page with a card per park. The app only
knows the parks baked into it, and nothing about the ones still ingesting.

CURRENT: `track_a.py index` walks config/parks.toml, reads the exported
files for counts (species, sightings, tour stops) where they exist, marks
the rest "planned", and writes app/public/data/parks.json, which the app
imports at build time. Each card's landscape photograph is the lead image
of the park's Wikipedia article, taken only when Wikimedia Commons reports a
licence that allows reuse with credit (public domain, CC0, CC BY, CC BY-SA)
and stored with artist, licence and the Commons file page, so the card can
print the credit like every other image on the site (ADR-0015).

CONSIDERED: iNaturalist animal photographs as card art (already licensed,
but a park card wants the place, not a marmot); NPS photo galleries (public
domain, but no API and no per-photo metadata to keep); no image at all.

UNRESOLVED: Commons' `Artist` field is free HTML and sometimes a paragraph;
it is stripped to text and cut at 80 characters. Lead images change when
editors change them; the index is re-run by hand, not on a schedule.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import requests

from .config import EXPORT_DIR, ROOT, load_parks

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "parkwild/0.1 (wildlife side project; https://github.com/Tlappas-23/parkwild)"}
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
# COMMONS_API — BORROWED (Wikimedia Commons Action API endpoint)
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# HERO_LICENCES — BORROWED (Commons' LicenseShortName values for works that may
# be reused with credit; matched as casefolded prefixes, so "CC BY-SA 4.0",
# "CC BY 2.0", "CC0", "Public domain" and "PD-USGov" all pass, "GFDL" and
# "Fair use" do not)
HERO_LICENCES = ("public domain", "pd", "cc0", "cc by")

# HERO_WIDTH — ARBITRARY (a card is at most about 600 px wide on a 2x screen)
HERO_WIDTH = 1280

# ARTIST_MAX — ARBITRARY (Commons' Artist field can be a paragraph; a credit line is not)
ARTIST_MAX = 80

# INDEX_PATH — DERIVED (imported by the app at build time, so it lives with the app's data)
INDEX_PATH = ROOT / "app" / "public" / "data" / "parks.json"


def strip_html(s: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def pick_licence(extmetadata: dict) -> dict | None:
    """The credit fields if the licence allows reuse, else None."""
    short = strip_html((extmetadata.get("LicenseShortName") or {}).get("value"))
    if not short or not short.casefold().startswith(HERO_LICENCES):
        return None
    artist = strip_html((extmetadata.get("Artist") or {}).get("value"))
    return {"license": short, "license_url": strip_html((extmetadata.get("LicenseUrl") or {}).get("value")),
            "artist": (artist[: ARTIST_MAX - 1] + "…") if len(artist) > ARTIST_MAX else artist or "unknown"}


def fetch_hero(article_title: str, *, session: requests.Session | None = None) -> dict | None:
    """Lead image of a Wikipedia article with its Commons licence, or None
    when there is no image or the licence does not allow reuse."""
    s = session or requests.Session()
    r = s.get(SUMMARY_URL.format(title=article_title.replace(" ", "_")), headers=HEADERS, timeout=30)
    if r.status_code != 200:
        log.warning("summary %s -> %d", article_title, r.status_code)
        return None
    j = r.json()
    thumb = (j.get("thumbnail") or {}).get("source")
    original = (j.get("originalimage") or {}).get("source")
    if not thumb or not original:
        return None
    # Some articles' "original" is itself a sized copy:
    # .../commons/thumb/a/ab/File.jpg/3840px-File.jpg. The file is the segment
    # before the size-prefixed one in that case (Shenandoah, Yellowstone).
    parts = original.split("?")[0].split("/")
    file_name = unquote(parts[-2] if "/thumb/" in original and len(parts) > 2 else parts[-1])
    q = s.get(COMMONS_API, params={"action": "query", "titles": f"File:{file_name}", "prop": "imageinfo",
                                   "iiprop": "extmetadata|url", "format": "json"}, headers=HEADERS, timeout=30)
    if q.status_code != 200:
        return None
    pages = (q.json().get("query") or {}).get("pages") or {}
    info = (next(iter(pages.values()), {}).get("imageinfo") or [{}])[0]
    lic = pick_licence(info.get("extmetadata") or {})
    if lic is None:
        log.info("%s: lead image %s not reusable (%s)", article_title, file_name,
                 strip_html(((info.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value")))
        return None
    url = re.sub(r"/\d+px-", f"/{HERO_WIDTH}px-", thumb.split("?")[0])
    return {"url": url, "page": info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/File:{file_name}",
            "source_article": ((j.get("content_urls") or {}).get("desktop") or {}).get("page", ""), **lic}


def _counts(export_dir: Path) -> dict:
    species = json.loads((export_dir / "species.json").read_text())["species"]
    cells = json.loads((export_dir / "cells.geojson").read_text())
    out = {"species": len(species), "sightings": sum(s["sightings"] for s in species), "cells": len(cells["features"]),
           "stops": None, "tour_source": None}
    lm = export_dir / "landmarks.json"
    if lm.exists():
        j = json.loads(lm.read_text())
        out["stops"] = len(j.get("tour", []))
        out["tour_source"] = j.get("tour_source")
    return out


def build_index(out_path: Path = INDEX_PATH, *, heroes: bool = True) -> dict:
    previous = {}
    if out_path.exists():
        previous = {p["key"]: p for p in json.loads(out_path.read_text()).get("parks", [])}
    session = requests.Session()
    parks = []
    for key, park in load_parks().items():
        d = EXPORT_DIR / key
        live = (d / "manifest.json").exists() and (d / "species.json").exists()
        entry = {"key": key, "name": park.name, "state": park.state, "status": "live" if live else "planned",
                 "species": None, "sightings": None, "cells": None, "stops": None, "tour_source": None, "hero": None}
        if live:
            entry.update(_counts(d))
        hero = (previous.get(key) or {}).get("hero")
        if hero is None and heroes:
            hero = fetch_hero(park.name, session=session)
            time.sleep(0.5)
        entry["hero"] = hero
        parks.append(entry)
    payload = {"generated": datetime.now(UTC).isoformat(timespec="seconds"),
               "attribution": "Park photographs: Wikimedia Commons, each under the licence printed on its card",
               "parks": parks}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    return {"parks": len(parks), "live": sum(p["status"] == "live" for p in parks),
            "heroes": sum(p["hero"] is not None for p in parks), "bytes": out_path.stat().st_size}
