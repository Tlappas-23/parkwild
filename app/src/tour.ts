// The virtual tour's arithmetic: which animals were recorded around a stop,
// and which way the camera should face. Pure functions; the map page and the
// tour panel both use them.
import { cellPhotos, speciesPhotos, type Photo } from "./photos";
import type { AmenitiesFile, AmenityItem, CellsFile, Landmark, LandmarksFile, PhotosCellsFile, PhotosSpeciesFile, RoadsFile, TrailItem } from "./types";

// TOUR_RADIUS_M — ASSUMED (a valley-scale neighbourhood around a viewpoint)
// Sightings within this distance of a stop count as "recorded here". 2.5 km
// is roughly what you can see from a pull-out; smaller and geyser-basin stops
// show nothing, larger and every stop lists the whole park.
// REVISIT IF: forest stops in the Smokies (short sightlines) look empty.
export const TOUR_RADIUS_M = 2500;
// TOUR_DWELL_MS — ARBITRARY (time to read a paragraph and glance at the photos)
export const TOUR_DWELL_MS = 14000;
// STOP_ZOOM / STOP_PITCH — ARBITRARY (standing above the stop, close enough
// to see the place: 12.4 / 60° then 13.3 read as too far; imagery is sharp to 16)
export const STOP_ZOOM = 14.4;
export const STOP_PITCH = 62;
// DRIVE_* — ARBITRARY (the road between stops from a driver's height: low
// zoom, steep pitch, distance compressed so a 20 km leg takes about ten
// seconds and a short one never less than four)
export const DRIVE_ZOOM = 14.8;
export const DRIVE_PITCH = 64;
export const DRIVE_SPEED_MS = 2200;      // virtual metres per second
export const DRIVE_MIN_MS = 4000;
export const DRIVE_MAX_MS = 14000;
// DRIVE_LOOKAHEAD_M — ARBITRARY (the camera faces this far up the road; shorter jitters on bends)
export const DRIVE_LOOKAHEAD_M = 120;
// DRIVE_MIN_LEG_M — ARBITRARY (a leg shorter than this is a hop, not a drive)
export const DRIVE_MIN_LEG_M = 250;

// The heading of the road at distance d: toward a point ahead, or, in the last
// stretch where nothing is ahead, from a point behind. The first version
// looked "ahead" to the end point itself and spun toward north on arrival.
export function headingAt(rs: Resampled, d: number, lookM: number): number {
  const ahead = Math.min(rs.total, d + lookM);
  if (ahead - d > 5) return bearingDeg(pointAt(rs, d), pointAt(rs, ahead));
  return bearingDeg(pointAt(rs, Math.max(0, d - lookM)), pointAt(rs, rs.total));
}
// ORBIT_PAUSE_MS — ARBITRARY (after the visitor turns the map, the tour keeps its hands off this long)
export const ORBIT_PAUSE_MS = 10000;
// ORBIT_DEG_PER_S — ARBITRARY (a slow turn around the stop for as long as the
// tour runs; about a quarter turn per dwell. The first version was one
// 45° animation that any tap on the map cancelled for good, E-044)
export const ORBIT_DEG_PER_S = 3.2;

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

// A place the drawer can open: anything with a name and a point. Trails also
// carry their length and take their geometry from the routing graph.
export interface Place { id: string; kind: string; name: string; lon: number; lat: number; detail?: string; lengthM?: number; wiki?: string | null; tags?: Record<string, string>; }
export interface NearItem { id: string; kind: string; label: string; detail: string; lon: number; lat: number; distM: number; lengthM?: number; wiki?: string | null; tags?: Record<string, string>; }
export function placeOf(it: NearItem): Place { return { id: it.id, kind: it.kind, name: it.label, lon: it.lon, lat: it.lat, detail: it.detail, lengthM: it.lengthM, wiki: it.wiki, tags: it.tags }; }
export function placeOfLandmark(l: Landmark): Place {
  const title = l.url ? decodeURIComponent(l.url.split("/wiki/")[1] ?? "").replace(/_/g, " ") : null;
  return { id: l.id, kind: l.kind, name: l.name, lon: l.lon, lat: l.lat, wiki: title || null, tags: l.ele_m ? { ele: String(l.ele_m) } : undefined };
}
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
  const wikiOf = (it: AmenityItem) => (it.tags.wikipedia?.startsWith("en:") ? it.tags.wikipedia.slice(3) : null);
  const item = (it: AmenityItem, d: number, detail?: string): NearItem =>
    ({ id: it.id, kind: it.kind, label: it.name, detail: detail ?? `${it.sub}${it.tags.ele ? ` · ${Math.round(+it.tags.ele).toLocaleString()} m` : ""} · ${fmtDist(d)}`,
       lon: it.lon, lat: it.lat, distM: d, wiki: wikiOf(it), tags: it.tags });
  const items = a.items;
  const features = near(items.filter((i) => i.kind === "feature"), NEAR_M).slice(0, PER_GROUP).map(({ it, d }) => item(it, d));
  const hike = near(items.filter((i) => i.kind === "trailhead"), NEAR_M).slice(0, PER_GROUP).map(({ it, d }) => item(it, d, `trailhead · ${fmtDist(d)}`));
  const trails = near(a.trails, NEAR_M).sort((x, y) => y.it.length_m - x.it.length_m).slice(0, PER_GROUP)
    .map(({ it, d }) => ({ id: it.id, kind: "trail", label: it.name, detail: `${(it.length_m / 1000).toFixed(1)} km of trail · ${fmtDist(d)} away`, lon: it.lon, lat: it.lat, distM: d, lengthM: it.length_m }));
  const camp = near(items.filter((i) => i.kind === "camp"), CAMP_M).slice(0, PER_GROUP).map(({ it, d }) => item(it, d, campDetail(it, d)));
  const stay = near(items.filter((i) => i.kind === "stay"), CAMP_M).slice(0, 3).map(({ it, d }) => item(it, d, `${it.sub} · ${fmtDist(d)}`));
  const facilities = near(items.filter((i) => ["viewpoint", "picnic", "info", "boat"].includes(i.kind)), NEAR_M).slice(0, PER_GROUP)
    .map(({ it, d }) => item(it, d, `${it.kind === "info" ? "visitor centre" : it.sub} · ${fmtDist(d)}`));
  const total = features.length + trails.length + hike.length + camp.length + stay.length + facilities.length;
  return { features, trails, hike, camp, stay, facilities, total };
}


// Every piece of a named trail in the routing graph, as polylines.
export function trailLines(roads: RoadsFile | null, name: string): number[][][] {
  if (!roads) return [];
  const idx = roads.names.indexOf(name);
  if (idx < 0) return [];
  return roads.edges.filter((e) => e[3] === 1 && e[5] === idx).map((e) => e[6]);
}

// Distance from a point to a polyline, metres, on a local flat projection.
function distToLineM(lon: number, lat: number, line: number[][]): number {
  const ky = 110_540, kx = 111_320 * Math.cos((lat * Math.PI) / 180);
  let best = Infinity;
  for (let i = 1; i < line.length; i++) {
    const ax = (line[i - 1][0] - lon) * kx, ay = (line[i - 1][1] - lat) * ky, bx = (line[i][0] - lon) * kx, by = (line[i][1] - lat) * ky;
    const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
    const t = len2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2)) : 0;
    const px = ax + t * dx, py = ay + t * dy;
    const d = Math.hypot(px, py);
    if (d < best) best = d;
  }
  return best;
}

// TRAIL_BUFFER_M — ASSUMED (what a walker on the trail could see or hear; one cell each side)
export const TRAIL_BUFFER_M = 300;

// Species recorded in the cells a trail passes through, same shape as nearbySpecies.
export function speciesNearLines(cells: CellsFile | null, lines: number[][][], bufferM = TRAIL_BUFFER_M, limit = 8): Nearby {
  if (!cells || lines.length === 0) return { list: [], total: 0, cells: 0, cellIds: [] };
  // Bounding box of the trail plus the buffer prunes most cells before the segment test.
  let w = 180, e = -180, s = 90, n = -90;
  for (const l of lines) for (const [x, y] of l) { w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y); }
  const dLat = bufferM / 110_540, dLon = bufferM / (111_320 * Math.cos(((s + n) / 2) * Math.PI / 180));
  const agg = new Map<number, NearbySpecies>();
  const cellIds: string[] = [];
  let total = 0, count = 0;
  for (const f of cells.features) {
    if (f.properties.coarsened) continue;
    const ring = f.geometry.coordinates[0], k = ring.length - 1;
    let cx = 0, cy = 0;
    for (let i = 0; i < k; i++) { cx += ring[i][0]; cy += ring[i][1]; }
    cx /= k; cy /= k;
    if (cx < w - dLon || cx > e + dLon || cy < s - dLat || cy > n + dLat) continue;
    if (!lines.some((l) => distToLineM(cx, cy, l) <= bufferM)) continue;
    count++;
    cellIds.push(f.properties.cell);
    total += f.properties.count;
    for (const en of f.properties.sp) {
      const cur = agg.get(en[0]) ?? { species: cells.species_index[en[0]].n, common: cells.species_index[en[0]].c, count: 0, hv: 0, mp: 0 };
      cur.count += en[1]; cur.hv += en[2]; cur.mp += en[3];
      agg.set(en[0], cur);
    }
  }
  return { list: [...agg.values()].sort((a, b) => b.count - a.count).slice(0, limit), total, cells: count, cellIds };
}


// A polyline resampled to even steps, with cumulative distance, so the drive
// can place the camera at any distance along it.
export interface Resampled { pts: number[][]; cum: number[]; total: number; }
// Points every stepM metres along a line, with their distance from the start.
// One running distance for the whole line. resample_v1 kept a per-segment
// "carry" and added it back at every vertex, so on an OSM road with a vertex
// every 10 to 50 m the distance table drifted by half a step per vertex; the
// camera driven off it crawled, then jumped, and its heading whipped around
// (the "map gets all messed up" report on the first drive, E-047).
export function resample(coords: number[][], stepM: number): Resampled {
  const pts: number[][] = [coords[0]];
  const cum: number[] = [0];
  let segStart = 0;          // distance from the start to the current vertex
  let next = stepM;          // distance of the next sample to place
  for (let i = 1; i < coords.length; i++) {
    const [ax, ay] = coords[i - 1], [bx, by] = coords[i];
    const seg = haversineM(ax, ay, bx, by);
    if (seg === 0) continue;
    while (next <= segStart + seg) {
      const f = (next - segStart) / seg;
      pts.push([ax + (bx - ax) * f, ay + (by - ay) * f]);
      cum.push(next);
      next += stepM;
    }
    segStart += seg;
  }
  pts.push(coords[coords.length - 1]); cum.push(segStart);
  return { pts, cum, total: segStart };
}
export function pointAt(rs: Resampled, d: number): [number, number] {
  if (d <= 0) return rs.pts[0] as [number, number];
  if (d >= rs.total) return rs.pts[rs.pts.length - 1] as [number, number];
  let lo = 0, hi = rs.cum.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (rs.cum[mid] <= d) lo = mid; else hi = mid; }
  const span = rs.cum[hi] - rs.cum[lo] || 1, f = (d - rs.cum[lo]) / span;
  const a = rs.pts[lo], b = rs.pts[hi];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
}
