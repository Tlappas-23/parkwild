"""Typical weather by month at a park's centre: climate.json.

The places page says when people go; the owner also wanted the weather. Live
conditions come from the browser at view time (Open-Meteo forecast API, free
and keyless). What can be precomputed is the climate: ten years of daily
weather at the park's busiest place (or its centre) from the Open-Meteo archive (ERA5),
folded into twelve monthly normals: typical high and low, rain, snow, and how
many days are wet. One request per park, refreshed with the fortnightly job
when the file is older than a season. Attribution: Open-Meteo.com, CC BY 4.0.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, date, datetime
from pathlib import Path

import requests

from .config import EXPORT_DIR, Park
from .export import write_park_manifest

log = logging.getLogger(__name__)

# ARCHIVE_URL — BORROWED (Open-Meteo historical weather API, ERA5, free, no key, CC BY 4.0)
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
# CLIMATE_YEARS — ARBITRARY (ten full years: enough to average out one odd year, recent enough to be today's climate)
CLIMATE_YEARS = 10
# WET_DAY_MM — BORROWED (the WMO threshold for a wet day)
WET_DAY_MM = 1.0
USER_AGENT = "parkwild/1.0 (https://github.com/Tlappas-23/parkwild)"


def monthly_normals(days: list[str], tmax: list[float | None], tmin: list[float | None], precip: list[float | None],
                    snow: list[float | None]) -> list[dict]:
    """Twelve rows: mean daily high and low, mean monthly rain and snow, wet days per month."""
    acc = [{"tmax": 0.0, "tmin": 0.0, "n": 0, "precip": 0.0, "snow": 0.0, "wet": 0, "years": set()} for _ in range(12)]
    for d, hi, lo, p, s in zip(days, tmax, tmin, precip, snow):
        m = int(d[5:7]) - 1
        a = acc[m]
        if hi is not None and lo is not None:
            a["tmax"] += hi
            a["tmin"] += lo
            a["n"] += 1
        a["precip"] += p or 0.0
        a["snow"] += s or 0.0
        a["wet"] += 1 if (p or 0.0) >= WET_DAY_MM else 0
        a["years"].add(d[:4])
    out = []
    for a in acc:
        y = max(1, len(a["years"]))
        out.append({"tmax": round(a["tmax"] / a["n"], 1) if a["n"] else None, "tmin": round(a["tmin"] / a["n"], 1) if a["n"] else None,
                    "precip_mm": round(a["precip"] / y), "snow_cm": round(a["snow"] / y, 1), "wet_days": round(a["wet"] / y)})
    return out


# RETRY_WAITS_S — ARBITRARY (a ten-year daily request is a heavy call; the archive answers 429 to a burst of them)
RETRY_WAITS_S = (5, 20, 60)


def fetch_daily(lat: float, lon: float, start: date, end: date, *, session: requests.Session) -> dict:
    params = {"latitude": lat, "longitude": lon, "start_date": start.isoformat(), "end_date": end.isoformat(),
              "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum", "timezone": "auto"}
    for attempt, wait in enumerate((*RETRY_WAITS_S, None)):
        r = session.get(ARCHIVE_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=60)
        if r.status_code in (429, 500, 502, 503, 504) and wait is not None:
            log.info("archive answered %s; waiting %ss (attempt %d)", r.status_code, wait, attempt + 1)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("unreachable")


def build_climate(park: Park, out_dir: Path | None = None, *, session: requests.Session | None = None, today: date | None = None) -> dict:
    out_dir = out_dir or EXPORT_DIR / park.key
    session = session or requests.Session()
    today = today or date.today()
    end = date(today.year - 1, 12, 31)
    start = date(end.year - CLIMATE_YEARS + 1, 1, 1)
    # Where visitors are, not the middle of the rectangle: the park's most
    # recorded place when places.json exists (Death Valley's bbox centre is a
    # mountain with a July high of 31 °C; its busiest place is on the valley
    # floor). The bbox centre is the fallback.
    lon = (park.bbox.min_lon + park.bbox.max_lon) / 2
    lat = (park.bbox.min_lat + park.bbox.max_lat) / 2
    at = "park centre"
    places_path = out_dir / "places.json"
    if places_path.exists():
        top = json.loads(places_path.read_text()).get("places") or []
        if top and top[0]["near"]["n"] > 0:
            lon, lat, at = top[0]["lon"], top[0]["lat"], top[0]["name"]
    j = fetch_daily(lat, lon, start, end, session=session)
    d = j["daily"]
    months = monthly_normals(d["time"], d["temperature_2m_max"], d["temperature_2m_min"], d["precipitation_sum"], d["snowfall_sum"])
    payload = {"park": park.key, "generated": datetime.now(UTC).isoformat(timespec="seconds"), "lat": round(lat, 4), "lon": round(lon, 4), "at": at,
               "elevation_m": j.get("elevation"), "years": [start.year, end.year], "source": "Open-Meteo.com (ERA5 reanalysis), CC BY 4.0",
               "months": months}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "climate.json").write_text(json.dumps(payload, separators=(",", ":")))
    write_park_manifest(out_dir, park.key)
    return {"at": at, "years": payload["years"], "elevation_m": payload["elevation_m"], "july_tmax": months[6]["tmax"], "january_tmin": months[0]["tmin"]}
