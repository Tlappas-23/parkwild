// Directions inside the park, computed in the browser over the road-and-trail
// graph the pipeline baked from OpenStreetMap (parkwild/roads.py). No routing
// service is used: none is free without a key, and a key in a static site is
// public. Shortest paths are Dijkstra; the visiting order is exact for small
// site lists and a good heuristic beyond that.
import type { RoadsFile } from "../data/types";

// SPEED_DRIVE_MS — ASSUMED (35 mph average on park roads: posted limits are
// 25 to 45 and traffic stops for animals) REVISIT IF: a park posts much lower.
export const SPEED_DRIVE_MS = 15.6;
// SPEED_WALK_MS — BORROWED (Naismith's rule on the flat, 5 km/h; no climb allowance)
export const SPEED_WALK_MS = 1.39;
// STOP_OVERHEAD_S — ARBITRARY (parking and walking to the viewpoint at each site)
export const STOP_OVERHEAD_S = 300;
// MAX_SITES / EXACT_SITES — ARBITRARY (Held-Karp is exact and instant up to
// EXACT_SITES; beyond that nearest-neighbour plus 2-opt; beyond MAX_SITES the
// panel refuses, a day has only so many hours)
export const MAX_SITES = 12;
export const EXACT_SITES = 9;
// FAR_SNAP_M — ASSUMED (a site is routed to the nearest node whatever the
// distance: a lake's point is its centre, and the road to its shore is the
// right answer; past this the leg says how far the point is from the road)
export const FAR_SNAP_M = 1000;

export type Mode = "drive" | "hike";
export interface Site {
  id: string;
  label: string;
  lon: number;
  lat: number;
  kind: "stop" | "landmark" | "cell" | "me";
}
export interface Leg {
  from: Site;
  to: Site;
  distanceM: number;
  seconds: number;
  coords: number[][];
}
export interface PlanResult {
  mode: Mode;
  order: Site[];
  legs: Leg[];
  distanceM: number;
  seconds: number;
  unreachable: Site[];
  snapM: Record<string, number>;
}

const KIND_ROAD = 0;

function metres(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const ky = 110_540,
    kx = 111_320 * Math.cos((((lat1 + lat2) / 2) * Math.PI) / 180);
  return Math.hypot((lon2 - lon1) * kx, (lat2 - lat1) * ky);
}

// A binary min-heap of [distance, node]; the graph is small, but a plan runs
// one Dijkstra per site and an array scan would still be felt on a phone.
class Heap {
  private a: [number, number][] = [];
  get size() {
    return this.a.length;
  }
  push(d: number, n: number) {
    const a = this.a;
    a.push([d, n]);
    let i = a.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (a[p][0] <= a[i][0]) break;
      [a[p], a[i]] = [a[i], a[p]];
      i = p;
    }
  }
  pop(): [number, number] {
    const a = this.a,
      top = a[0],
      last = a.pop()!;
    if (a.length) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1,
          r = l + 1;
        let m = i;
        if (l < a.length && a[l][0] < a[m][0]) m = l;
        if (r < a.length && a[r][0] < a[m][0]) m = r;
        if (m === i) break;
        [a[m], a[i]] = [a[i], a[m]];
        i = m;
      }
    }
    return top;
  }
}

export interface Shortest {
  dist: Float64Array;
  prevNode: Int32Array;
  prevEdge: Int32Array;
}

export class Router {
  private adj: [number, number][][]; // node -> [neighbour, edge]
  private roadNode: Uint8Array; // 1 if any road edge touches the node

  constructor(readonly file: RoadsFile) {
    const n = file.nodes.length;
    this.adj = Array.from({ length: n }, () => []);
    this.roadNode = new Uint8Array(n);
    file.edges.forEach((e, i) => {
      const [a, b, , kind, oneway] = e;
      this.adj[a].push([b, i]);
      if (!oneway) this.adj[b].push([a, i]);
      if (kind === KIND_ROAD) {
        this.roadNode[a] = 1;
        this.roadNode[b] = 1;
      }
    });
  }

  // Nearest graph node; in drive mode only nodes a road touches, so a trailhead
  // is chosen over the trail itself.
  snap(lon: number, lat: number, mode: Mode): { node: number; distM: number } {
    let best = -1,
      bestD = Infinity;
    const nodes = this.file.nodes;
    for (let i = 0; i < nodes.length; i++) {
      if (mode === "drive" && !this.roadNode[i]) continue;
      const d = metres(lon, lat, nodes[i][0], nodes[i][1]);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    return { node: best, distM: bestD };
  }

  shortest(source: number, mode: Mode): Shortest {
    const n = this.file.nodes.length;
    const dist = new Float64Array(n).fill(Infinity);
    const prevNode = new Int32Array(n).fill(-1),
      prevEdge = new Int32Array(n).fill(-1);
    const heap = new Heap();
    dist[source] = 0;
    heap.push(0, source);
    while (heap.size) {
      const [d, u] = heap.pop();
      if (d > dist[u]) continue;
      for (const [v, ei] of this.adj[u]) {
        const e = this.file.edges[ei];
        if (mode === "drive" && e[3] !== KIND_ROAD) continue;
        const nd = d + e[2];
        if (nd < dist[v]) {
          dist[v] = nd;
          prevNode[v] = u;
          prevEdge[v] = ei;
          heap.push(nd, v);
        }
      }
    }
    return { dist, prevNode, prevEdge };
  }

  // Coordinates from the source of `s` to `target`, edge geometry stitched in
  // the direction travelled.
  path(s: Shortest, target: number): number[][] {
    const parts: number[][][] = [];
    let v = target;
    while (s.prevEdge[v] >= 0) {
      const e = this.file.edges[s.prevEdge[v]],
        u = s.prevNode[v];
      const coords = e[0] === u ? e[6] : [...e[6]].reverse();
      parts.push(coords);
      v = u;
    }
    parts.reverse();
    const out: number[][] = [];
    for (const p of parts)
      for (let i = 0; i < p.length; i++) {
        if (out.length && i === 0) continue;
        out.push(p[i]);
      }
    return out;
  }
}

const routers = new WeakMap<RoadsFile, Router>();
export function routerFor(file: RoadsFile): Router {
  let r = routers.get(file);
  if (!r) {
    r = new Router(file);
    routers.set(file, r);
  }
  return r;
}

// Exact open-path Held-Karp: start fixed, every site once, end anywhere.
function orderExact(cost: number[][]): number[] {
  const n = cost.length - 1; // index 0 is the start
  const full = (1 << n) - 1;
  const dp = Array.from({ length: 1 << n }, () => new Float64Array(n).fill(Infinity));
  const par = Array.from({ length: 1 << n }, () => new Int8Array(n).fill(-1));
  for (let j = 0; j < n; j++) dp[1 << j][j] = cost[0][j + 1];
  for (let mask = 1; mask <= full; mask++) {
    for (let j = 0; j < n; j++) {
      if (!(mask & (1 << j)) || dp[mask][j] === Infinity) continue;
      for (let k = 0; k < n; k++) {
        if (mask & (1 << k)) continue;
        const nm = mask | (1 << k),
          c = dp[mask][j] + cost[j + 1][k + 1];
        if (c < dp[nm][k]) {
          dp[nm][k] = c;
          par[nm][k] = j;
        }
      }
    }
  }
  let end = 0;
  for (let j = 1; j < n; j++) if (dp[full][j] < dp[full][end]) end = j;
  const order: number[] = [];
  let mask = full,
    j = end;
  while (j >= 0) {
    order.push(j);
    const pj = par[mask][j];
    mask &= ~(1 << j);
    j = pj;
  }
  return order.reverse();
}

// Nearest neighbour from the start, then 2-opt on the directed cost.
function orderHeuristic(cost: number[][]): number[] {
  const n = cost.length - 1;
  const left = new Set(Array.from({ length: n }, (_, i) => i));
  const order: number[] = [];
  let cur = 0;
  while (left.size) {
    let best = -1,
      bd = Infinity;
    for (const j of left)
      if (cost[cur][j + 1] < bd) {
        bd = cost[cur][j + 1];
        best = j;
      }
    order.push(best);
    left.delete(best);
    cur = best + 1;
  }
  const total = (o: number[]) => o.reduce((acc, j, i) => acc + cost[i === 0 ? 0 : o[i - 1] + 1][j + 1], 0);
  let improved = true;
  while (improved) {
    improved = false;
    for (let i = 0; i < n - 1; i++)
      for (let k = i + 1; k < n; k++) {
        const cand = [...order.slice(0, i), ...order.slice(i, k + 1).reverse(), ...order.slice(k + 1)];
        if (total(cand) + 1e-9 < total(order)) {
          order.splice(0, n, ...cand);
          improved = true;
        }
      }
  }
  return order;
}

export function planRoute(router: Router, start: Site, sites: Site[], mode: Mode): PlanResult {
  const points = [start, ...sites];
  const snapM: Record<string, number> = {};
  const nodes = points.map((p) => {
    const s = router.snap(p.lon, p.lat, mode);
    snapM[p.id] = s.distM;
    return s.node;
  });
  const reachable: number[] = []; // indices into points that found a node at all
  const unreachable: Site[] = [];
  points.forEach((p, i) => {
    if (i === 0 || nodes[i] >= 0) reachable.push(i);
    else unreachable.push(p);
  });
  const shortest = reachable.map((i) => router.shortest(nodes[i], mode));
  // Sites the network cannot reach from the start in this mode also drop out.
  const keep: number[] = [reachable[0]];
  for (let r = 1; r < reachable.length; r++) {
    if (shortest[0].dist[nodes[reachable[r]]] < Infinity) keep.push(reachable[r]);
    else unreachable.push(points[reachable[r]]);
  }
  const idx = keep.map((i) => reachable.indexOf(i));
  const cost = idx.map((ri) => idx.map((rj) => shortest[ri].dist[nodes[reachable[rj]]]));
  const n = keep.length - 1;
  const order = n === 0 ? [] : n <= EXACT_SITES ? orderExact(cost) : orderHeuristic(cost);
  const speed = mode === "drive" ? SPEED_DRIVE_MS : SPEED_WALK_MS;
  const legs: Leg[] = [];
  let prev = 0;
  for (const j of order) {
    const to = j + 1;
    const s = shortest[idx[prev]];
    const distanceM = cost[prev][to];
    legs.push({
      from: points[keep[prev]],
      to: points[keep[to]],
      distanceM,
      seconds: distanceM / speed + STOP_OVERHEAD_S,
      coords: router.path(s, nodes[keep[to]]),
    });
    prev = to;
  }
  return {
    mode,
    order: order.map((j) => points[keep[j + 1]]),
    legs,
    distanceM: legs.reduce((a, l) => a + l.distanceM, 0),
    seconds: legs.reduce((a, l) => a + l.seconds, 0),
    unreachable,
    snapM,
  };
}

// Exposed for automated checks in a real browser; not part of the UI.
if (typeof window !== "undefined")
  (window as unknown as { __parkwildRoute?: unknown }).__parkwildRoute = { routerFor, planRoute };

export function fmtKm(m: number): string {
  return m < 950 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(m < 10_000 ? 1 : 0)} km`;
}
export function fmtTime(s: number): string {
  const min = Math.round(s / 60);
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
}
// OpenStreetMap's own directions page, free and keyless, for turn-by-turn on the road.
export function directionsUrl(from: Site, to: Site): string {
  return `https://www.openstreetmap.org/directions?from=${from.lat.toFixed(5)}%2C${from.lon.toFixed(5)}&to=${to.lat.toFixed(5)}%2C${to.lon.toFixed(5)}`;
}
