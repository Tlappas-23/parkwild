// Matching a search against the cross-park species index: common name,
// scientific name, and every other name a park recorded it under.
import type { SpeciesAcrossParks } from "../data/types";

export function indexMatches(e: SpeciesAcrossParks, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return [e.c ?? "", e.n, ...e.other].some((n) => n.toLowerCase().includes(needle));
}
