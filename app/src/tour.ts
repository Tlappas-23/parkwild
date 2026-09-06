// The virtual tour's arithmetic: which animals were recorded around a stop,
// and which way the camera should face. Pure functions; the map page and the
// tour panel both use them.
import { cellPhotos, speciesPhotos, type Photo } from "./photos";
import type { AmenitiesFile, AmenityItem, CellsFile, Landmark, LandmarksFile, PhotosCellsFile, PhotosSpeciesFile, TrailItem } from "./types";

// TOUR_RADIUS_M — ASSUMED (a valley-scale neighbourhood around a viewpoint)
// Sightings within this distance of a stop count as "recorded here". 2.5 km
// is roughly what you can see from a pull-out; smaller and geyser-basin stops
// show nothing, larger and every stop lists the whole park.
// REVISIT IF: forest stops in the Smokies (short sightlines) look empty.
export const TOUR_RADIUS_M = 2500;
// TOUR_DWELL_MS — ARBITRARY (time to read a paragraph and glance at the photos)
export const TOUR_DWELL_MS = 14000;
// STOP_ZOOM / STOP_PITCH — ARBITRARY (standing on the hillside above the
// stop: the first version sat at 12.4 / 60°, which the owner read as too far)
export const STOP_ZOOM = 13.3;
export const STOP_PITCH = 64;
// ORBIT_DEG / ORBIT_MS — ARBITRARY (a slow part-turn around the stop while the
// narration runs, so the map moves during the tour; a drag stops it)
export const ORBIT_DEG = 45;
export const ORBIT_MS = TOUR_DWELL_MS;

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
export interface Nearby { list: NearbySpecies[]; total: number; cells: number; cellIds: string[]; }

// Species recorded in open-coordinate cells within `radiusM` of a point.
// Coarsened (sensitive-species) cells are skipped on purpose: a 3 km cell
// says nothing about a particular viewpoint, and pinning a grizzly to a
// landmark is exactly what the suppression list exists to prevent.
export function nearbySpecies(cells: CellsFile | null, lon: number, lat: number, radiusM = TOUR_RADIUS_M, limit = 6): Nearby {
  if (!cells) return { list: [], total: 0, cells: 0, cellIds: [] };
  const agg = new Map<number, NearbySpecies>();
  const cellIds: string[] = [];
  let total = 0, n = 0;
  for (const f of cells.features) {
    if (f.properties.coarsened) continue;
    const ring = f.geometry.coordinates[0];
    const k = ring.length - 1;                        // the last vertex repeats the first
    let cx = 0, cy = 0;
    for (let i = 0; i < k; i++) { cx += ring[i][0]; cy += ring[i][1]; }
    if (haversineM(lon, lat, cx / k, cy / k) > radiusM) continue;
    n++;
    cellIds.push(f.properties.cell);
    total += f.properties.count;
    for (const e of f.properties.sp) {
      const cur = agg.get(e[0]) ?? { species: cells.species_index[e[0]].n, common: cells.species_index[e[0]].c, count: 0, hv: 0, mp: 0 };
      cur.count += e[1]; cur.hv += e[2]; cur.mp += e[3];
      agg.set(e[0], cur);
    }
  }
  return { list: [...agg.values()].sort((a, b) => b.count - a.count).slice(0, limit), total, cells: n, cellIds };
}

// A photograph of the species taken inside the stop's radius when one exists:
// the cell strips keep one per species per cell and the galleries know their
// cell, so most stops can show an animal seen right there. Otherwise the
// species' best photograph from anywhere in the park, and the card says so.
export function photoNear(species: string, cellIds: string[], photosCells: PhotosCellsFile | null, photosSpecies: PhotosSpeciesFile | null): { photo: Photo; near: boolean } | null {
  for (const id of cellIds) {
    const p = cellPhotos(photosCells, id).find((x) => x.species === species);
    if (p) return { photo: p, near: true };
  }
  const near = new Set(cellIds);
  const gallery = speciesPhotos(photosSpecies, species);
  const g = gallery.find((p) => p.cell !== null && near.has(p.cell));
  if (g) return { photo: g, near: true };
  return gallery[0] ? { photo: gallery[0], near: false } : null;
}


// NEAR_M / CAMP_M — ASSUMED (what counts as "around here": features, trails and
// facilities within a short walk or drive; a campground or lodge is a longer
// drive away and there are few of them, so the net is wider)
export const NEAR_M = 3000;
export const CAMP_M = 12000;
// PER_GROUP — ARBITRARY (a card, not a directory)
export const PER_GROUP = 6;

export interface NearItem { id: string; kind: string; label: string; detail: string; lon: number; lat: number; distM: number; }
export interface Things { features: NearItem[]; trails: NearItem[]; hike: NearItem[]; camp: NearItem[]; stay: NearItem[]; facilities: NearItem[]; total: number; }

function campDetail(it: AmenityItem, distM: number): string {
  const t = it.tags;
  const bits = [fmtDist(distM)];
  if (t.backcountry === "yes") bits.push("backcountry");
  if (t.capacity) bits.push(`${t.capacity} sites`);
  if (t.fee) bits.push(t.fee === "no" ? "free" : "fee");
  if (t.reservation) bits.push(t.reservation === "no" ? "first come" : `reservation ${t.reservation}`);
  if (t.seasonal && t.seasonal !== "no") bits.push("seasonal");
  return bits.join(" · ");
}
export function fmtDist(m: number): string { return m < 950 ? `${Math.round(m / 50) * 50} m` : `${(m / 1000).toFixed(1)} km`; }

// Everything worth doing around a point, grouped, nearest first (trails by
// length), capped per group. Items keep their coordinates so the map can mark
// them and the planner can add them.
export function thingsNear(a: AmenitiesFile | null, lon: number, lat: number): Things {
  const empty: Things = { features: [], trails: [], hike: [], camp: [], stay: [], facilities: [], total: 0 };
  if (!a) return empty;
  const near = <T extends AmenityItem | TrailItem>(list: T[], radius: number) =>
    list.map((it) => ({ it, d: haversineM(lon, lat, it.lon, it.lat) })).filter((x) => x.d <= radius).sort((x, y) => x.d - y.d);
  const item = (it: AmenityItem, d: number, detail?: string): NearItem =>
    ({ id: it.id, kind: it.kind, label: it.name, detail: detail ?? `${it.sub}${it.tags.ele ? ` · ${Math.round(+it.tags.ele).toLocaleString()} m` : ""} · ${fmtDist(d)}`, lon: it.lon, lat: it.lat, distM: d });
  const items = a.items;
  const features = near(items.filter((i) => i.kind === "feature"), NEAR_M).slice(0, PER_GROUP).map(({ it, d }) => item(it, d));
  const hike = near(items.filter((i) => i.kind === "trailhead"), NEAR_M).slice(0, PER_GROUP).map(({ it, d }) => item(it, d, `trailhead · ${fmtDist(d)}`));
  const trails = near(a.trails, NEAR_M).sort((x, y) => y.it.length_m - x.it.length_m).slice(0, PER_GROUP)
    .map(({ it, d }) => ({ id: it.id, kind: "trail", label: it.name, detail: `${(it.length_m / 1000).toFixed(1)} km of trail · ${fmtDist(d)} away`, lon: it.lon, lat: it.lat, distM: d }));
  const camp = near(items.filter((i) => i.kind === "camp"), CAMP_M).slice(0, PER_GROUP).map(({ it, d }) => item(it, d, campDetail(it, d)));
  const stay = near(items.filter((i) => i.kind === "stay"), CAMP_M).slice(0, 3).map(({ it, d }) => item(it, d, `${it.sub} · ${fmtDist(d)}`));
  const facilities = near(items.filter((i) => ["viewpoint", "picnic", "info", "boat"].includes(i.kind)), NEAR_M).slice(0, PER_GROUP)
    .map(({ it, d }) => item(it, d, `${it.kind === "info" ? "visitor centre" : it.sub} · ${fmtDist(d)}`));
  const total = features.length + trails.length + hike.length + camp.length + stay.length + facilities.length;
  return { features, trails, hike, camp, stay, facilities, total };
}
