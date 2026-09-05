// The virtual tour's arithmetic: which animals were recorded around a stop,
// and which way the camera should face. Pure functions; the map page and the
// tour panel both use them.
import type { CellsFile, Landmark, LandmarksFile } from "./types";

// TOUR_RADIUS_M — ASSUMED (a valley-scale neighbourhood around a viewpoint)
// Sightings within this distance of a stop count as "recorded here". 2.5 km
// is roughly what you can see from a pull-out; smaller and geyser-basin stops
// show nothing, larger and every stop lists the whole park.
// REVISIT IF: forest stops in the Smokies (short sightlines) look empty.
export const TOUR_RADIUS_M = 2500;
// TOUR_DWELL_MS — ARBITRARY (time to read a paragraph and glance at the photos)
export const TOUR_DWELL_MS = 11000;
// STOP_ZOOM / STOP_PITCH — ARBITRARY (a hillside view: relief visible, cells still readable)
export const STOP_ZOOM = 12.4;
export const STOP_PITCH = 60;

const EARTH_R = 6371000;

export function haversineM(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const toRad = Math.PI / 180;
  const dLat = (lat2 - lat1) * toRad, dLon = (lon2 - lon1) * toRad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_R * Math.asin(Math.sqrt(a));
}

// Initial bearing from one point to another, degrees clockwise from north.
export function bearingDeg(from: [number, number], to: [number, number]): number {
  const toRad = Math.PI / 180;
  const lat1 = from[1] * toRad, lat2 = to[1] * toRad, dLon = (to[0] - from[0]) * toRad;
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

// The stops in visiting order. The landmarks file lists ids; the records carry the details.
export function tourStops(file: LandmarksFile | null): Landmark[] {
  if (!file) return [];
  const byId = new Map(file.landmarks.map((l) => [l.id, l]));
  return file.tour.map((id) => byId.get(id)).filter((l): l is Landmark => !!l);
}

// The camera looks toward the next stop, the way a walker faces the trail
// ahead; at the last stop it keeps the heading it arrived on.
export function stopBearing(stops: Landmark[], i: number): number {
  const cur = stops[i], next = stops[i + 1], prev = stops[i - 1];
  if (!cur) return 0;
  if (next) return bearingDeg([cur.lon, cur.lat], [next.lon, next.lat]);
  if (prev) return bearingDeg([prev.lon, prev.lat], [cur.lon, cur.lat]);
  return 0;
}

export interface NearbySpecies { species: string; common: string | null; count: number; hv: number; mp: number; }
export interface Nearby { list: NearbySpecies[]; total: number; cells: number; }

// Species recorded in open-coordinate cells within `radiusM` of a point.
// Coarsened (sensitive-species) cells are skipped on purpose: a 3 km cell
// says nothing about a particular viewpoint, and pinning a grizzly to a
// landmark is exactly what the suppression list exists to prevent.
export function nearbySpecies(cells: CellsFile | null, lon: number, lat: number, radiusM = TOUR_RADIUS_M, limit = 6): Nearby {
  if (!cells) return { list: [], total: 0, cells: 0 };
  const agg = new Map<number, NearbySpecies>();
  let total = 0, n = 0;
  for (const f of cells.features) {
    if (f.properties.coarsened) continue;
    const ring = f.geometry.coordinates[0];
    const k = ring.length - 1;                        // the last vertex repeats the first
    let cx = 0, cy = 0;
    for (let i = 0; i < k; i++) { cx += ring[i][0]; cy += ring[i][1]; }
    if (haversineM(lon, lat, cx / k, cy / k) > radiusM) continue;
    n++;
    total += f.properties.count;
    for (const e of f.properties.sp) {
      const cur = agg.get(e[0]) ?? { species: cells.species_index[e[0]].n, common: cells.species_index[e[0]].c, count: 0, hv: 0, mp: 0 };
      cur.count += e[1]; cur.hv += e[2]; cur.mp += e[3];
      agg.set(e[0], cur);
    }
  }
  return { list: [...agg.values()].sort((a, b) => b.count - a.count).slice(0, limit), total, cells: n };
}
