// One store for UI state. Data is loaded once per park; filters are applied
// in selectors so the map and the species pages agree on what "filtered" means.
import { create } from "zustand";
import type { BiasFile, BoundaryFile, CellFeature, CellsFile, LandmarksFile, Manifest, PhotosCellsFile, PhotosSpeciesFile, SpeciesFile } from "./types";
import { availableParks, loadCellPhotos, loadPark } from "./data";

export type Page = "map" | "species" | "about";
export type Basemap = "terrain" | "satellite";
export interface TourState { active: boolean; stop: number; playing: boolean; }

interface State {
  park: string;
  parkName: string;
  page: Page;
  cells: CellsFile | null;
  species: SpeciesFile | null;
  bias: BiasFile | null;
  photosSpecies: PhotosSpeciesFile | null;
  photosCells: PhotosCellsFile | null;
  landmarks: LandmarksFile | null;
  boundary: BoundaryFile | null;
  manifest: Manifest | null;
  error: string | null;
  speciesFilter: string | null;      // scientific name, or null for all
  yearRange: [number, number];        // inclusive
  selectedCell: string | null;
  selectedSpecies: string | null;
  reducedMotion: boolean;
  basemap: Basemap;
  terrain3d: boolean;
  tour: TourState;
  tourPrevBasemap: Basemap | null;   // what the visitor had before the tour switched to satellite
  setPage: (p: Page) => void;
  setSpeciesFilter: (s: string | null) => void;
  setYearRange: (r: [number, number]) => void;
  selectCell: (c: string | null) => void;
  selectSpecies: (s: string | null) => void;
  setPark: (key: string) => void;
  setBasemap: (b: Basemap) => void;
  setTerrain3d: (on: boolean) => void;
  startTour: () => void;
  endTour: () => void;
  tourGo: (i: number) => void;
  tourNext: () => void;
  tourPrev: () => void;
  tourPlay: (on: boolean) => void;
  load: () => Promise<void>;
  ensureCellPhotos: () => Promise<void>;
}

export const PARKS = availableParks();
const prefersReduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ?park= makes a link open on the right park; anything unknown falls back to
// the first baked park (Yellowstone).
function initialPark(): string {
  try {
    const q = new URLSearchParams(window.location.search).get("park");
    if (q && PARKS.some((p) => p.key === q)) return q;
  } catch { /* no window */ }
  return PARKS[0]?.key ?? "yellowstone";
}
function nameOf(key: string): string { return PARKS.find((p) => p.key === key)?.name ?? key; }
function readBasemap(): Basemap {
  try { return localStorage.getItem("parkwild:basemap") === "satellite" ? "satellite" : "terrain"; } catch { return "terrain"; }
}
const NO_TOUR: TourState = { active: false, stop: 0, playing: false };

export const useStore = create<State>((set, get) => ({
  park: initialPark(),
  parkName: nameOf(initialPark()),
  page: "map",
  cells: null,
  species: null,
  bias: null,
  photosSpecies: null,
  photosCells: null,
  landmarks: null,
  boundary: null,
  manifest: null,
  error: null,
  speciesFilter: null,
  yearRange: [1900, 2100],
  selectedCell: null,
  selectedSpecies: null,
  reducedMotion: prefersReduced,
  basemap: readBasemap(),
  terrain3d: !prefersReduced,        // relief on by default; off for people who asked the OS for less motion
  tour: NO_TOUR,
  tourPrevBasemap: null,
  setPage: (page) => set({ page, selectedSpecies: page === "species" ? get().selectedSpecies : null }),
  setSpeciesFilter: (speciesFilter) => set({ speciesFilter }),
  setYearRange: (yearRange) => set({ yearRange }),
  selectCell: (selectedCell) => { set({ selectedCell }); if (selectedCell) void get().ensureCellPhotos(); },
  selectSpecies: (selectedSpecies) => set({ selectedSpecies, page: "species" }),
  // Switching parks drops everything loaded, resets every filter, rewrites the
  // URL so the link is shareable, and loads again.
  setPark: (park) => {
    if (park === get().park || !PARKS.some((p) => p.key === park)) return;
    set({ park, parkName: nameOf(park), cells: null, species: null, bias: null, photosSpecies: null, photosCells: null,
          landmarks: null, boundary: null, manifest: null, error: null, speciesFilter: null, selectedCell: null,
          selectedSpecies: null, tour: NO_TOUR });
    try { const u = new URL(window.location.href); u.searchParams.set("park", park); window.history.replaceState(null, "", u.toString()); } catch { /* ignore */ }
    void get().load();
  },
  setBasemap: (basemap) => { set({ basemap }); try { localStorage.setItem("parkwild:basemap", basemap); } catch { /* ignore */ } },
  setTerrain3d: (terrain3d) => set({ terrain3d }),
  // The tour is the 3D walk: relief on and imagery under it, the way a flyover
  // reads; leaving the tour puts the visitor's own basemap choice back.
  startTour: () => set({ tour: { active: true, stop: 0, playing: false }, page: "map", selectedCell: null, terrain3d: true,
                         tourPrevBasemap: get().tour.active ? get().tourPrevBasemap : get().basemap, basemap: "satellite" }),
  endTour: () => set({ tour: NO_TOUR, basemap: get().tourPrevBasemap ?? get().basemap, tourPrevBasemap: null }),
  tourGo: (stop) => set({ tour: { ...get().tour, active: true, stop }, page: "map", selectedCell: null, terrain3d: true,
                          tourPrevBasemap: get().tour.active ? get().tourPrevBasemap : get().basemap, basemap: "satellite" }),
  tourNext: () => {
    const n = get().landmarks?.tour.length ?? 0, t = get().tour;
    set({ tour: t.stop < n - 1 ? { ...t, stop: t.stop + 1 } : { ...t, playing: false } });
  },
  tourPrev: () => { const t = get().tour; if (t.stop > 0) set({ tour: { ...t, stop: t.stop - 1 } }); },
  tourPlay: (playing) => set({ tour: { ...get().tour, playing } }),
  load: async () => {
    const park = get().park;
    try {
      const { cells, species, bias, photosSpecies, landmarks, boundary, manifest } = await loadPark(park);
      if (get().park !== park) return;         // the visitor switched parks while this one was loading
      let lo = 2100, hi = 1900;
      for (const f of cells.features) {
        if (f.properties.y0 !== null) lo = Math.min(lo, f.properties.y0);
        if (f.properties.y1 !== null) hi = Math.max(hi, f.properties.y1);
      }
      set({ cells, species, bias, photosSpecies, landmarks, boundary, manifest, error: null, yearRange: lo <= hi ? [lo, hi] : [1900, 2100] });
    } catch (e) {
      if (get().park === park) set({ error: (e as Error).message });
    }
  },
  ensureCellPhotos: async () => {
    if (get().photosCells) return;
    const park = get().park;
    try {
      const photosCells = await loadCellPhotos(park, get().manifest);
      if (get().park === park) set({ photosCells });
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

// Does a species match a search? Common name, the names that lost the vote
// ("elk" finds Wapiti), the scientific name, and its synonyms.
export function speciesMatches(s: { common_name: string | null; other_names?: string[]; scientific_name: string; aliases: string[] }, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return [s.common_name ?? "", ...(s.other_names ?? []), s.scientific_name, ...s.aliases].some((n) => n.toLowerCase().includes(needle));
}
