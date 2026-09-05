// One store for UI state. Data is loaded once per park; filters are applied
// in selectors so the map and the species pages agree on what "filtered" means.
import { create } from "zustand";
import type { BiasFile, CellFeature, CellsFile, Manifest, PhotosCellsFile, PhotosSpeciesFile, SpeciesFile } from "./types";
import { loadCellPhotos, loadPark } from "./data";

export type Page = "map" | "species" | "about";

interface State {
  park: string;
  page: Page;
  cells: CellsFile | null;
  species: SpeciesFile | null;
  bias: BiasFile | null;
  photosSpecies: PhotosSpeciesFile | null;
  photosCells: PhotosCellsFile | null;
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
  ensureCellPhotos: () => Promise<void>;
}

const prefersReduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const useStore = create<State>((set, get) => ({
  park: "yellowstone",
  page: "map",
  cells: null,
  species: null,
  bias: null,
  photosSpecies: null,
  photosCells: null,
  manifest: null,
  error: null,
  speciesFilter: null,
  yearRange: [1900, 2100],
  selectedCell: null,
  selectedSpecies: null,
  reducedMotion: prefersReduced,
  setPage: (page) => set({ page, selectedSpecies: page === "species" ? get().selectedSpecies : null }),
  setSpeciesFilter: (speciesFilter) => set({ speciesFilter }),
  setYearRange: (yearRange) => set({ yearRange }),
  selectCell: (selectedCell) => { set({ selectedCell }); if (selectedCell) void get().ensureCellPhotos(); },
  selectSpecies: (selectedSpecies) => set({ selectedSpecies, page: "species" }),
  load: async () => {
    try {
      const { cells, species, bias, photosSpecies, manifest } = await loadPark(get().park);
      let lo = 2100, hi = 1900;
      for (const f of cells.features) {
        if (f.properties.y0 !== null) lo = Math.min(lo, f.properties.y0);
        if (f.properties.y1 !== null) hi = Math.max(hi, f.properties.y1);
      }
      set({ cells, species, bias, photosSpecies, manifest, error: null, yearRange: lo <= hi ? [lo, hi] : [1900, 2100] });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },
  ensureCellPhotos: async () => {
    if (get().photosCells) return;
    try {
      set({ photosCells: await loadCellPhotos(get().park, get().manifest) });
    } catch (e) {
      console.warn("[parkwild] cell photos unavailable:", (e as Error).message);
    }
  },
}));

// A cell is shown if its date span overlaps the year range and, with a species
// filter, if it holds that species; the feature's counts are then swapped for
// that species' own numbers. Cells carry spans, not dates, so overlap is the
// honest test: the cell *may* have sightings in range.
export function filteredFeatures(cells: CellsFile | null, speciesFilter: string | null, yearRange: [number, number]): CellFeature[] {
  if (!cells) return [];
  const [lo, hi] = yearRange;
  const idx = speciesFilter ? cells.species_index.findIndex((e) => e.n === speciesFilter) : -1;
  if (speciesFilter && idx < 0) return [];
  const out: CellFeature[] = [];
  for (const f of cells.features) {
    const p = f.properties;
    if (idx >= 0) {
      const e = p.sp.find((x) => x[0] === idx);
      if (!e) continue;
      const first = e[4] ?? lo, last = e[5] ?? hi;
      if (last < lo || first > hi) continue;
      out.push({ ...f, properties: { ...p, count: e[1], hv: e[2], mp: e[3], y0: e[4], y1: e[5], sp: [e] } });
    } else {
      const first = p.y0 ?? lo, last = p.y1 ?? hi;
      if (last < lo || first > hi) continue;
      out.push(f);
    }
  }
  return out;
}
