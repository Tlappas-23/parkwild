// The Places page's vocabulary: which kinds belong to which group, what to
// call them, and how to say when people go from a month histogram.
import type { PlaceRec } from "../data/types";

export type PlaceGroup = "all" | "trails" | "sites" | "camping" | "facilities";
export type PlaceSort = "recorded" | "readers" | "az" | "longest";

const SITE_KINDS = new Set([
  "peak",
  "attraction",
  "place",
  "feature",
  "viewpoint",
  "waterfall",
  "lake",
  "spring",
  "geyser",
  "valley",
  "canyon",
  "arch",
  "cave",
  "glacier",
  "island",
  "beach",
  "meadow",
  "pass",
  "river",
]);
const CAMP_KINDS = new Set(["camp", "stay"]);
const FACILITY_KINDS = new Set(["trailhead", "picnic", "info", "boat"]);

export function groupOf(p: PlaceRec): Exclude<PlaceGroup, "all"> {
  if (p.kind === "trail") return "trails";
  if (CAMP_KINDS.has(p.kind)) return "camping";
  if (FACILITY_KINDS.has(p.kind)) return "facilities";
  return SITE_KINDS.has(p.kind) || p.src === "landmark" ? "sites" : "facilities";
}

const LABELS: Record<string, string> = {
  trail: "Trail",
  peak: "Peak",
  attraction: "Attraction",
  place: "Place",
  feature: "Natural feature",
  viewpoint: "Viewpoint",
  camp: "Campground",
  stay: "Lodging",
  trailhead: "Trailhead",
  picnic: "Picnic area",
  info: "Visitor centre",
  boat: "Boat launch",
  waterfall: "Waterfall",
  lake: "Lake",
  spring: "Hot spring",
  geyser: "Geyser",
  valley: "Valley",
  canyon: "Canyon",
  arch: "Arch",
  cave: "Cave",
  glacier: "Glacier",
};
export function kindLabel(p: PlaceRec): string {
  const sub = p.sub && p.sub !== p.kind ? p.sub : null;
  return LABELS[p.kind] ?? (sub ? sub.replace(/_/g, " ") : p.kind.replace(/_/g, " "));
}

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// MIN_FOR_MONTHS — ARBITRARY (fewer records than this and the busiest month is noise)
export const MIN_FOR_MONTHS = 12;

// "Busiest May to Jul" when the top three months touch, "Busiest Jun, Sep, Oct" when they do not.
export function busiest(months: number[]): { label: string; peak: number } | null {
  const total = months.reduce((a, b) => a + b, 0);
  if (total < MIN_FOR_MONTHS) return null;
  const order = months.map((n, i) => [n, i] as const).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  const peak = order[0][1];
  const top = order
    .slice(0, 3)
    .filter(([n]) => n > 0)
    .map(([, i]) => i)
    .sort((a, b) => a - b);
  if (
    top.length === 3 &&
    (top[2] - top[0] === 2 ||
      (top[0] === 0 && top[1] === 1 && top[2] === 11) ||
      (top[0] === 0 && top[1] === 10 && top[2] === 11))
  ) {
    const seq = top[2] - top[0] === 2 ? top : [top[1] === 1 ? 11 : 10, top[1] === 1 ? 0 : 11, top[1] === 1 ? 1 : 0];
    return { label: `Busiest ${MONTHS[seq[0]]} to ${MONTHS[seq[2]]}`, peak };
  }
  return { label: `Busiest ${top.map((i) => MONTHS[i]).join(", ")}`, peak };
}

export function sortPlaces(list: PlaceRec[], sort: PlaceSort): PlaceRec[] {
  const a = list.slice();
  if (sort === "az") a.sort((x, y) => x.name.localeCompare(y.name));
  else if (sort === "longest") a.sort((x, y) => (y.length_m ?? 0) - (x.length_m ?? 0) || y.near.n - x.near.n);
  else if (sort === "readers") a.sort((x, y) => (y.views_pm ?? -1) - (x.views_pm ?? -1) || y.near.n - x.near.n);
  else a.sort((x, y) => y.near.n - x.near.n || x.name.localeCompare(y.name));
  return a;
}

export function placeMatches(p: PlaceRec, q: string): boolean {
  const needle = q.trim().toLowerCase();
  return !needle || p.name.toLowerCase().includes(needle) || kindLabel(p).toLowerCase().includes(needle);
}
