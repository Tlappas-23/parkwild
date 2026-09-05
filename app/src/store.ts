// One store for UI state. Data is loaded once per park; filters are applied
// in selectors so the map and the species pages agree on what "filtered" means.
import { create } from "zustand";
import type { CellFeature, CellsFile, Manifest, SpeciesFile } from "./types";
import { loadPark } from "./data";

export type Page = "map" | "species" | "about";

interface State {
  park: string;
  page: Page;
  cells: CellsFile | null;
  species: SpeciesFile | null;
  manifest: Manifest | null;
  error: string | null;
  speciesFilter: string | null;      // scientific name, or null for all
  yearRange: [number, number];        // inclusive
  selectedCell: string | null;
  selectedSpecies: string | null;
  reducedMotion: boolean;
  setPage: (p: Page) => void;
  setSpeciesFilter: (s: string | null) => void;
  setYearRange: (r: [number, number]) => void;
  selectCell: (c: string | null) => void;
  selectSpecies: (s: string | null) => void;
  load: () => Promise<void>;
}

const prefersReduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const useStore = create<State>((set, get) => ({
  park: "yellowstone",
  page: "map",
  cells: null,
  species: null,
  manifest: null,
  error: null,
  speciesFilter: null,
  yearRange: [1900, 2100],
  selectedCell: null,
  selectedSpecies: null,
  reducedMotion: prefersReduced,
  setPage: (page) => set({ page }),
  setSpeciesFilter: (speciesFilter) => set({ speciesFilter }),
  setYearRange: (yearRange) => set({ yearRange }),
  selectCell: (selectedCell) => set({ selectedCell }),
  selectSpecies: (selectedSpecies) => set({ selectedSpecies, page: "species" }),
  load: async () => {
    try {
      const { cells, species, manifest } = await loadPark(get().park);
      // Default the year scrubber to the data's real span.
      let lo = 2100, hi = 1900;
      for (const f of cells.features) {
        if (f.properties.first) lo = Math.min(lo, +f.properties.first.slice(0, 4));
        if (f.properties.last) hi = Math.max(hi, +f.properties.last.slice(0, 4));
      }
      set({ cells, species, manifest, error: null, yearRange: lo <= hi ? [lo, hi] : [1900, 2100] });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },
}));

// A cell feature is shown if it matches the species filter and its date span
// overlaps the year range. Cells carry a span, not individual dates, so the
// overlap test is the honest one: the cell *may* have sightings in range.
export function filteredFeatures(cells: CellsFile | null, speciesFilter: string | null, yearRange: [number, number]): CellFeature[] {
  if (!cells) return [];
  const [lo, hi] = yearRange;
  return cells.features.filter((f) => {
    const p = f.properties;
    if (speciesFilter && p.species !== speciesFilter) return false;
    const first = p.first ? +p.first.slice(0, 4) : lo;
    const last = p.last ? +p.last.slice(0, 4) : hi;
    return last >= lo && first <= hi;
  });
}
